from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AnalysisAttempt,
    ConstructionObject,
    DayEvaluation,
    Inspection,
    Snapshot,
    SnapshotImage,
)
from .api.w2_common import current_schedule, schedule_payload


PROJECT_ROOT = Path(__file__).resolve().parents[2]
THRESHOLDS_PATH = PROJECT_ROOT / "config/analysis/thresholds.v1.json"
RULES_VERSION = "day-rules-v1"


@lru_cache
def thresholds() -> dict[str, Any]:
    return json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))


def nearest_control_slot(times: list[str], observed_time: str) -> str:
    hour, minute = (int(part) for part in observed_time.split(":"))
    observed_minutes = hour * 60 + minute

    def key(slot: str) -> tuple[int, int]:
        slot_hour, slot_minute = (int(part) for part in slot.split(":"))
        slot_minutes = slot_hour * 60 + slot_minute
        return abs(slot_minutes - observed_minutes), slot_minutes

    return min(times, key=key)


def _latest_attempt(db: Session, snapshot_id: str) -> AnalysisAttempt | None:
    return db.scalar(
        select(AnalysisAttempt)
        .where(
            AnalysisAttempt.snapshot_id == snapshot_id,
            AnalysisAttempt.state == "completed",
            AnalysisAttempt.normalized_response.is_not(None),
        )
        .order_by(AnalysisAttempt.attempt_number.desc())
    )


def _active_inspection(
    inspections: list[Inspection], plan_item_id: str, evaluation_date: date
) -> Inspection | None:
    matches = [
        item
        for item in inspections
        if item.plan_item_id == plan_item_id
        and item.observed_date <= evaluation_date <= (item.valid_until or item.observed_date)
    ]
    return max(matches, key=lambda item: (item.observed_date, item.created_at), default=None)


def _profile_is_configured(plan_item: dict[str, Any]) -> bool:
    profile = plan_item.get("profile") or {}
    return bool(profile.get("strong_features") or profile.get("additional_features"))


def calculate_day(
    db: Session,
    object_item: ConstructionObject,
    evaluation_date: date,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    schedule = current_schedule(db, object_item.id, evaluation_date)
    day_start = datetime.combine(evaluation_date, time.min)
    day_end = day_start + timedelta(days=1)
    snapshots = list(
        db.scalars(
            select(Snapshot)
            .where(
                Snapshot.object_id == object_item.id,
                Snapshot.observed_at >= day_start,
                Snapshot.observed_at < day_end,
                Snapshot.state.in_(["completed", "partial"]),
            )
            .order_by(Snapshot.uploaded_at)
        ).all()
    )
    latest_by_slot: dict[str, Snapshot] = {}
    for snapshot in snapshots:
        if snapshot.control_slot in schedule.times:
            latest_by_slot[snapshot.control_slot] = snapshot

    latest_snapshot = max(snapshots, key=lambda item: item.uploaded_at, default=None)
    if latest_snapshot and latest_snapshot.plan_snapshot:
        plan_snapshot = latest_snapshot.plan_snapshot
    else:
        from .analysis import build_plan_snapshot

        plan_snapshot = build_plan_snapshot(db, object_item, evaluation_date)

    inspections = list(
        db.scalars(
            select(Inspection)
            .where(
                Inspection.object_id == object_item.id,
                Inspection.observed_date <= evaluation_date,
            )
            .order_by(Inspection.observed_date, Inspection.created_at)
        ).all()
    )
    positive_threshold = float(thresholds()["model_evidence"]["positive_confidence"])
    absence_threshold = float(
        thresholds()["model_evidence"]["explicit_absence_confidence"]
    )
    stages: list[dict[str, Any]] = []

    for plan_item in plan_snapshot.get("plan_items", []):
        cells: list[dict[str, Any]] = []
        counted_hashes: set[str] = set()
        positive_intervals = 0
        usable_intervals = 0
        for slot in schedule.times:
            snapshot = latest_by_slot.get(slot)
            if snapshot is None:
                cells.append({"slot": slot, "state": "missing", "snapshot_id": None})
                continue
            attempt = _latest_attempt(db, snapshot.id)
            normalized = attempt.normalized_response if attempt else None
            if not normalized:
                cells.append(
                    {
                        "slot": slot,
                        "state": "uncovered",
                        "snapshot_id": snapshot.id,
                        "reason": "analysis_unavailable",
                    }
                )
                continue
            stage = next(
                (
                    item
                    for item in normalized.get("stage_evidence", [])
                    if item.get("plan_item_id") == plan_item["plan_item_id"]
                ),
                None,
            )
            observations = {
                item.get("camera_id"): item
                for item in normalized.get("camera_observations", [])
            }
            linked_cameras = set(plan_item.get("camera_ids") or [])
            suitable_cameras = [
                camera_id
                for camera_id in linked_cameras
                if observations.get(camera_id, {}).get("quality") in {"good", "acceptable"}
            ]
            profile_ready = _profile_is_configured(plan_item)
            if not stage or not suitable_cameras or not profile_ready:
                cells.append(
                    {
                        "slot": slot,
                        "state": "uncovered",
                        "snapshot_id": snapshot.id,
                        "reason": (
                            "profile_missing"
                            if not profile_ready
                            else "camera_coverage_insufficient"
                        ),
                    }
                )
                continue

            confidence = float(stage.get("confidence", 0))
            cell: dict[str, Any] = {
                "slot": slot,
                "snapshot_id": snapshot.id,
                "analysis_attempt_id": attempt.id,
                "confidence": confidence,
                "model_status": stage.get("status"),
                "explanation": stage.get("explanation", ""),
                "limitations": stage.get("limitations", []),
            }
            if stage.get("status") == "positive" and confidence >= positive_threshold:
                evidence_ids = set(stage.get("evidence_item_ids", []))
                evidence = [
                    item
                    for item in normalized.get("evidence_items", [])
                    if item.get("evidence_id") in evidence_ids
                    and item.get("polarity") == "positive"
                ]
                image_ids = {item.get("image_id") for item in evidence}
                hashes = {
                    item.sha256
                    for item in db.scalars(
                        select(SnapshotImage).where(
                            SnapshotImage.snapshot_id == snapshot.id,
                            SnapshotImage.id.in_(image_ids),
                        )
                    ).all()
                }
                independent = bool(hashes - counted_hashes)
                cell.update(
                    {
                        "state": "positive",
                        "independent": independent,
                        "evidence_items": evidence,
                    }
                )
                if independent:
                    positive_intervals += 1
                    counted_hashes.update(hashes)
                usable_intervals += 1
            elif stage.get("status") == "neutral" and confidence >= absence_threshold:
                cell.update({"state": "none", "independent": True, "evidence_items": []})
                usable_intervals += 1
            else:
                cell.update(
                    {
                        "state": "uncovered",
                        "reason": (
                            "conflict_requires_review"
                            if stage.get("status") == "conflict"
                            else "confidence_below_threshold"
                        ),
                    }
                )
            cells.append(cell)

        inspection = _active_inspection(inspections, plan_item["plan_item_id"], evaluation_date)
        if inspection:
            status = {
                "confirmed": "inspection_confirmed",
                "rejected": "inspection_rejected",
                "note": "inspection_note",
            }[inspection.verdict]
            source = {
                "type": "inspection",
                "inspection_id": inspection.id,
                "author": inspection.author,
                "observed_date": inspection.observed_date.isoformat(),
            }
        elif plan_item.get("confirmation_method") == "inspection":
            status = "awaiting_inspection"
            source = {"type": "inspection_pending"}
        elif plan_item.get("observability") == "no":
            status = "outside_visual_control"
            source = {"type": "rules"}
        elif positive_intervals >= schedule.confirmation_threshold:
            status = "confirmed"
            source = {"type": "cameras"}
        elif positive_intervals == 0 and usable_intervals >= schedule.absence_threshold:
            status = "possible_deviation"
            source = {"type": "cameras"}
        else:
            status = "insufficient_data"
            source = {"type": "cameras"}

        stages.append(
            {
                "plan_item_id": plan_item["plan_item_id"],
                "stage_code": plan_item["stage_code"],
                "stage_name": plan_item["stage_name"],
                "children": plan_item.get("children", []),
                "observability": plan_item["observability"],
                "confirmation_method": plan_item["confirmation_method"],
                "status": status,
                "source": source,
                "positive_intervals": positive_intervals,
                "usable_intervals": usable_intervals,
                "required_positive": schedule.confirmation_threshold,
                "required_absence": schedule.absence_threshold,
                "cells": cells,
            }
        )

    result = {
        "object_id": object_item.id,
        "date": evaluation_date.isoformat(),
        "rules_version": RULES_VERSION,
        "schedule_version": schedule.version,
        "times": list(schedule.times),
        "received": len(latest_by_slot),
        "expected": len(schedule.times),
        "stages": stages,
    }
    if persist:
        frozen_schedule = schedule_payload(schedule)
        frozen_schedule["effective_from"] = frozen_schedule["effective_from"].isoformat()
        frozen_schedule["created_at"] = frozen_schedule["created_at"].isoformat()
        row = db.scalar(
            select(DayEvaluation).where(
                DayEvaluation.object_id == object_item.id,
                DayEvaluation.evaluation_date == evaluation_date,
            )
        )
        if row is None:
            row = DayEvaluation(
                object_id=object_item.id,
                evaluation_date=evaluation_date,
                rules_version=RULES_VERSION,
                schedule_snapshot=frozen_schedule,
                plan_snapshot=plan_snapshot,
                result=result,
            )
            db.add(row)
        else:
            row.rules_version = RULES_VERSION
            row.schedule_snapshot = frozen_schedule
            row.plan_snapshot = plan_snapshot
            row.result = result
            row.calculated_at = datetime.utcnow()
        db.flush()
    return result
