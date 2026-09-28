from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Camera, Snapshot, SnapshotImage, TemporalComparison


MIN_SIGNAL_DAYS = 3
MIN_DAILY_SPAN_HOURS = 3
MIN_COMPARISON_CONFIDENCE = 0.7


def _equipment_type_key(value: str) -> str:
    """Compare common names for the same machine without changing the model's answer."""
    normalized = " ".join(value.casefold().replace("ё", "е").split())
    if normalized in {"excavator", "экскаватор", "гусеничный экскаватор"}:
        return "excavator"
    return normalized


def _usable_unchanged(item: TemporalComparison | None) -> bool:
    if item is None or item.state != "completed" or not item.result:
        return False
    result = item.result
    return (
        result.get("status") == "unchanged"
        and float(result.get("confidence", 0)) >= MIN_COMPARISON_CONFIDENCE
        and result.get("equipment_type") not in {None, "", "unknown"}
    )


def calculate_movement_signals(
    db: Session, object_id: str, evaluation_date: date
) -> list[dict[str, Any]]:
    start_date = evaluation_date - timedelta(days=30)
    rows = db.execute(
        select(SnapshotImage, Snapshot)
        .join(Snapshot, Snapshot.id == SnapshotImage.snapshot_id)
        .where(
            Snapshot.object_id == object_id,
            Snapshot.state.in_(["completed", "partial"]),
            Snapshot.observed_at >= datetime.combine(start_date, time.min),
            Snapshot.observed_at
            < datetime.combine(evaluation_date + timedelta(days=1), time.min),
        )
        .order_by(Snapshot.observed_at)
    ).all()
    images_by_camera_day: dict[str, dict[date, list[tuple[SnapshotImage, Snapshot]]]] = (
        defaultdict(lambda: defaultdict(list))
    )
    for image, snapshot in rows:
        images_by_camera_day[image.camera_id][snapshot.observed_at.date()].append(
            (image, snapshot)
        )

    comparisons = list(
        db.scalars(
            select(TemporalComparison).where(
                TemporalComparison.object_id == object_id
            )
        ).all()
    )
    by_pair = {
        (item.first_image_id, item.second_image_id): item for item in comparisons
    }
    signals: list[dict[str, Any]] = []

    for camera_id, days in images_by_camera_day.items():
        daily: dict[date, dict[str, Any]] = {}
        for day, images in days.items():
            if len(images) < 2:
                continue
            images.sort(key=lambda item: (item[1].observed_at, item[0].id))
            first_image, first_snapshot = images[0]
            last_image, last_snapshot = images[-1]
            span_hours = (
                last_snapshot.observed_at - first_snapshot.observed_at
            ).total_seconds() / 3600
            if span_hours < MIN_DAILY_SPAN_HOURS:
                continue
            within: list[TemporalComparison] = []
            for (left_image, _), (right_image, _) in zip(images, images[1:]):
                if left_image.fov_revision != right_image.fov_revision:
                    within = []
                    break
                comparison = by_pair.get((left_image.id, right_image.id))
                if not _usable_unchanged(comparison):
                    within = []
                    break
                within.append(comparison)
            if len(within) != len(images) - 1:
                continue
            equipment_types = {
                _equipment_type_key(item.result["equipment_type"]) for item in within
            }
            if len(equipment_types) != 1:
                continue
            daily[day] = {
                "images": images,
                "first_image": first_image,
                "first_snapshot": first_snapshot,
                "last_image": last_image,
                "last_snapshot": last_snapshot,
                "within": within,
                "equipment_type_key": equipment_types.pop(),
                "equipment_type": within[-1].result["equipment_type"],
            }

        run: list[tuple[date, dict[str, Any]]] = []
        comparisons_in_run: list[TemporalComparison] = []
        best_run: (
            tuple[
                list[tuple[date, dict[str, Any]]],
                list[TemporalComparison],
            ]
            | None
        ) = None
        for day in sorted(daily):
            current = daily[day]
            if not run:
                run = [(day, current)]
                comparisons_in_run = list(current["within"])
            else:
                # Ночное сравнение (вечер → утро) не используется: к утру техника обычно
                # стоит на стоянке, и совпадение положения ничего не говорит о работе днём.
                # Дни связываются по календарю, ракурсу и типу техники.
                previous_day, previous = run[-1]
                continues = (
                    day == previous_day + timedelta(days=1)
                    and current["first_image"].fov_revision
                    == previous["last_image"].fov_revision
                    and current["equipment_type_key"] == previous["equipment_type_key"]
                )
                if continues:
                    run.append((day, current))
                    comparisons_in_run.extend(current["within"])
                else:
                    run = [(day, current)]
                    comparisons_in_run = list(current["within"])
            if day == evaluation_date and len(run) >= MIN_SIGNAL_DAYS:
                best_run = (list(run), list(comparisons_in_run))

        if best_run is None:
            continue
        run, used_comparisons = best_run
        camera = db.get(Camera, camera_id)
        image_rows = []
        for _, item in run:
            image_rows.extend(item["images"])
        signals.append(
            {
                "camera_id": camera_id,
                "camera_name": camera.name,
                "equipment_type": run[-1][1]["equipment_type"],
                "start_date": run[0][0].isoformat(),
                "end_date": run[-1][0].isoformat(),
                "idle_days": len(run),
                "observation_count": len(image_rows),
                "comparison_ids": [item.id for item in used_comparisons],
                "images": [
                    {
                        "id": image.id,
                        "snapshot_id": snapshot.id,
                        "observed_at": snapshot.observed_at,
                        "storage_key": image.storage_key,
                        "camera_name": image.camera_name_snapshot,
                    }
                    for image, snapshot in image_rows
                ],
                "note": "Снимки не доказывают непрерывный простой между проверками.",
            }
        )
    return signals
