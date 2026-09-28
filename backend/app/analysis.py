from __future__ import annotations

import json
import logging
import re
from dataclasses import replace
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .analysis_contract.client import (
    ProviderConfig,
    ProviderError,
    build_request_payload,
    call_provider,
    extract_normalized_response,
    usage_metrics,
)
from .analysis_contract.contract import ContractError, validate_analysis
from .config import Settings
from .models import (
    AnalysisAttempt,
    Camera,
    ConstructionObject,
    PlanItem,
    Snapshot,
    SnapshotImage,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "config/analysis/analysis-response.schema.v1.json"
PROMPT_PATH = PROJECT_ROOT / "config/analysis/prompts/construction-analysis.v2.md"
PROMPT_VERSION = "construction-analysis-v2"
CONTRACT_VERSION = "analysis-response-v1"
CATALOG_VERSION = "w2-demo-catalog-v1"

logger = logging.getLogger(__name__)


@lru_cache
def analysis_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache
def analysis_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def provider_config(settings: Settings) -> ProviderConfig:
    return ProviderConfig(
        provider=settings.ai_provider,
        base_url=settings.ai_base_url.rstrip("/"),
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        api_style=settings.ai_api_style,
        reasoning_effort=settings.ai_reasoning_effort,
        timeout_seconds=settings.ai_timeout_seconds,
        image_max_edge=settings.ai_image_max_edge,
        image_jpeg_quality=settings.ai_image_jpeg_quality,
        input_price_per_million=settings.ai_input_price_per_million,
        output_price_per_million=settings.ai_output_price_per_million,
    )


def fallback_config(settings: Settings) -> ProviderConfig | None:
    primary = provider_config(settings)
    model = settings.ai_fallback_model.strip()
    if not model or model == primary.model:
        return None
    style = settings.ai_fallback_api_style.strip() or primary.api_style
    return replace(
        primary,
        provider=settings.ai_fallback_provider.strip() or primary.provider,
        base_url=(settings.ai_fallback_base_url.strip() or primary.base_url).rstrip("/"),
        api_key=settings.ai_fallback_api_key.strip() or primary.api_key,
        model=model,
        api_style=style,
        reasoning_effort=settings.ai_fallback_reasoning_effort.strip(),
        input_price_per_million=settings.ai_fallback_input_price_per_million,
        output_price_per_million=settings.ai_fallback_output_price_per_million,
    )


def attempt_plan(settings: Settings) -> list[ProviderConfig]:
    """Порядок попыток: основная модель N раз, затем резервная N раз."""
    per_model = max(1, settings.ai_attempts_per_model)
    plan = [provider_config(settings)] * per_model
    fallback = fallback_config(settings)
    if fallback is not None:
        plan += [fallback] * per_model
    return plan


def _feature_code(stage_code: str, group: str, index: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", stage_code.casefold()).strip("_") or "stage"
    return f"{base}_{group}_{index + 1}"


def _normalize_profile(stage_code: str, profile: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(profile.get("strong_features"), list):
        return dict(profile)

    strong = [
        {"code": _feature_code(stage_code, "strong", index), "description": description}
        for index, description in enumerate(profile.get("strong_signs", []))
        if isinstance(description, str) and description.strip()
    ]
    additional = [
        {"code": _feature_code(stage_code, "additional", index), "description": description}
        for index, description in enumerate(profile.get("additional_signs", []))
        if isinstance(description, str) and description.strip()
    ]
    return {
        "strong_features": strong,
        "additional_features": additional,
        "typical_equipment": list(profile.get("typical_equipment", [])),
        "minimum_equipment": profile.get("minimum_equipment", 0),
        "decision_note": profile.get(
            "decision_note",
            "Одна единица техники без контекста сцены этап не подтверждает.",
        ),
    }


def _merge_profiles(stage_code: str, rows: list[PlanItem]) -> dict[str, Any]:
    profiles = [_normalize_profile(item.stage_code, item.profile_snapshot or {}) for item in rows]
    return {
        "strong_features": list(
            {
                item["code"]: item
                for profile in profiles
                for item in profile.get("strong_features", [])
            }.values()
        ),
        "additional_features": list(
            {
                item["code"]: item
                for profile in profiles
                for item in profile.get("additional_features", [])
            }.values()
        ),
        "typical_equipment": list(
            dict.fromkeys(
                equipment
                for profile in profiles
                for equipment in profile.get("typical_equipment", [])
            )
        ),
        "minimum_equipment": max(
            (profile.get("minimum_equipment", 0) for profile in profiles),
            default=0,
        ),
        "decision_note": f"Объединённый профиль этапа {stage_code}.",
    }


def build_plan_snapshot(
    db: Session,
    object_item: ConstructionObject,
    observed_date: date,
) -> dict[str, Any]:
    cameras = list(
        db.scalars(
            select(Camera)
            .where(Camera.object_id == object_item.id, Camera.is_active.is_(True))
            .order_by(Camera.sort_order, Camera.created_at)
        ).all()
    )
    rows = list(
        db.scalars(
            select(PlanItem).where(
                PlanItem.object_id == object_item.id,
                PlanItem.is_archived.is_(False),
            )
        ).all()
    )
    children_by_parent: dict[str, list[PlanItem]] = {}
    for row in rows:
        if row.parent_id:
            children_by_parent.setdefault(row.parent_id, []).append(row)

    plan_items = []
    for item in sorted(
        [row for row in rows if row.parent_id is None],
        key=lambda row: (row.sort_order, row.created_at),
    ):
        if not (item.start_date <= observed_date <= item.end_date):
            continue
        children = children_by_parent.get(item.id, [])
        profile = (
            _merge_profiles(item.stage_code, children)
            if children
            else _normalize_profile(item.stage_code, item.profile_snapshot or {})
        )
        camera_ids = list(item.camera_ids or [])
        if children:
            camera_ids = list(dict.fromkeys(camera for child in children for camera in child.camera_ids))
        plan_items.append(
            {
                "plan_item_id": item.id,
                "stage_code": item.stage_code,
                "stage_name": item.name,
                "start_date": item.start_date.isoformat(),
                "end_date": item.end_date.isoformat(),
                "camera_ids": camera_ids,
                "observability": item.observability,
                "confirmation_method": item.confirmation_method,
                "visual_class": item.stage_code,
                "profile": profile,
                "version": item.version,
                "children": [
                    {
                        "plan_item_id": child.id,
                        "stage_code": child.stage_code,
                        "stage_name": child.name,
                    }
                    for child in sorted(
                        children, key=lambda row: (row.sort_order, row.created_at)
                    )
                ],
            }
        )

    return {
        "contract_version": CONTRACT_VERSION,
        "prompt_version": PROMPT_VERSION,
        "catalog_version": CATALOG_VERSION,
        "object": {
            "id": object_item.id,
            "name": object_item.name,
            "object_type": object_item.object_type,
            "timezone": object_item.timezone,
        },
        "cameras": [
            {
                "camera_id": camera.id,
                "camera_code": camera.code,
                "name": camera.name,
                "zone": camera.zone,
                "view_description": (camera.passport or {}).get("view_description", ""),
                "coverage": (camera.passport or {}).get("coverage", []),
                "fov_revision": camera.fov_revision,
            }
            for camera in cameras
        ],
        "plan_items": plan_items,
    }


def build_analysis_context(
    snapshot: Snapshot,
    images: list[SnapshotImage],
    storage: Any,
) -> dict[str, Any]:
    frozen = dict(snapshot.plan_snapshot or {})
    return {
        "fixture_version": f"snapshot-{snapshot.id}",
        "contract_version": frozen["contract_version"],
        "prompt_version": frozen["prompt_version"],
        "catalog_version": frozen["catalog_version"],
        "object": {
            **frozen["object"],
            "observed_at": snapshot.observed_at.isoformat(),
        },
        "cameras": frozen["cameras"],
        "plan_items": [
            {key: value for key, value in item.items() if key not in {"version", "children"}}
            for item in frozen["plan_items"]
        ],
        "images": [
            {
                "image_id": image.id,
                "camera_id": image.camera_id,
                "sha256": image.sha256,
                "media_type": image.content_type,
                "content": storage.get(image.storage_key),
            }
            for image in images
        ],
    }


def recover_interrupted_analyses(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as db:
        snapshots = db.scalars(
            select(Snapshot).where(Snapshot.state.in_(["queued", "analyzing"]))
        ).all()
        attempts = db.scalars(
            select(AnalysisAttempt).where(AnalysisAttempt.state.in_(["queued", "analyzing"]))
        ).all()
        now = datetime.utcnow()
        for snapshot in snapshots:
            snapshot.state = "error"
        for attempt in attempts:
            attempt.state = "error"
            attempt.error_code = "process_interrupted"
            attempt.error_detail = "Анализ был прерван перезапуском сервиса. Запустите повторно."
            attempt.finished_at = now
        if snapshots or attempts:
            db.commit()


def _next_attempt(
    db: Session,
    snapshot: Snapshot,
    config: ProviderConfig,
    number: int,
) -> AnalysisAttempt:
    attempt = AnalysisAttempt(
        snapshot_id=snapshot.id,
        attempt_number=number,
        state="queued",
        provider=config.provider,
        model=config.model,
        prompt_version=PROMPT_VERSION,
    )
    db.add(attempt)
    db.flush()
    return attempt


def refresh_day(db: Session, snapshot: Snapshot) -> None:
    """Пересчитать итог дня после нового анализа; сбой пишется в журнал, а не глушится."""
    from .day_rules import calculate_day

    try:
        calculate_day(db, snapshot.object, snapshot.observed_at.date())
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Итог дня не пересчитан: object=%s date=%s",
            snapshot.object_id,
            snapshot.observed_at.date(),
        )


def run_analysis_job(
    session_factory: sessionmaker[Session],
    storage: Any,
    settings: Settings,
    snapshot_id: str,
    initial_attempt_id: str,
) -> None:
    plan = attempt_plan(settings)
    step = 0
    attempt_id = initial_attempt_id
    while True:
        config = plan[step]
        with session_factory() as db:
            snapshot = db.get(Snapshot, snapshot_id)
            attempt = db.get(AnalysisAttempt, attempt_id)
            if snapshot is None or attempt is None:
                return
            images = list(
                db.scalars(
                    select(SnapshotImage)
                    .where(SnapshotImage.snapshot_id == snapshot.id)
                    .order_by(SnapshotImage.camera_id)
                ).all()
            )
            snapshot.state = "analyzing"
            attempt.state = "analyzing"
            attempt.provider = config.provider
            attempt.model = config.model
            db.commit()

            try:
                context = build_analysis_context(snapshot, images, storage)
                payload = build_request_payload(config, context, analysis_schema(), analysis_prompt())
                raw, headers, duration_ms = call_provider(config, payload)
                attempt.raw_response = raw
                metrics = usage_metrics(
                    raw,
                    config,
                    duration_ms,
                    headers.get("x-request-id") or str(raw.get("id", "")),
                )
                attempt.request_id = metrics["request_id"] or None
                attempt.duration_ms = metrics["duration_ms"]
                attempt.input_tokens = metrics["input_tokens"]
                attempt.output_tokens = metrics["output_tokens"]
                attempt.estimated_cost = (
                    str(metrics["estimated_cost"])
                    if metrics["estimated_cost"] is not None
                    else None
                )
                normalized = extract_normalized_response(raw, config.api_style)
                validate_analysis(normalized, context)
                attempt.normalized_response = normalized
                attempt.state = "completed"
                attempt.finished_at = datetime.utcnow()
                observations = normalized.get("camera_observations", [])
                snapshot.state = (
                    "partial"
                    if any(item.get("quality") == "unreadable" for item in observations)
                    else "completed"
                )
                db.commit()
                refresh_day(db, snapshot)
                return
            except (ContractError, ProviderError) as exc:
                attempt.state = "error"
                attempt.error_code = (
                    "invalid_model_response" if isinstance(exc, ContractError) else "provider_error"
                )
                attempt.error_detail = str(exc)
                attempt.finished_at = datetime.utcnow()
                if step + 1 < len(plan):
                    step += 1
                    retry = _next_attempt(db, snapshot, plan[step], attempt.attempt_number + 1)
                    snapshot.state = "queued"
                    db.commit()
                    attempt_id = retry.id
                    continue
                snapshot.state = "error"
                db.commit()
                return
            except Exception as exc:
                logger.exception("Анализ снимка %s завершился внутренней ошибкой", snapshot_id)
                attempt.state = "error"
                attempt.error_code = "internal_error"
                attempt.error_detail = f"{type(exc).__name__}: {exc}"
                attempt.finished_at = datetime.utcnow()
                snapshot.state = "error"
                db.commit()
                return
