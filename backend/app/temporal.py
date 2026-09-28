from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .analysis import attempt_plan
from .analysis_contract.client import (
    ProviderError,
    build_request_payload,
    call_provider,
    extract_normalized_response,
    usage_metrics,
)
from .analysis_contract.contract import ContractError
from .config import Settings
from .models import Camera, ConstructionObject, Snapshot, SnapshotImage, TemporalComparison


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "config/analysis/temporal-comparison-response.schema.v1.json"
PROMPT_PATH = PROJECT_ROOT / "config/analysis/prompts/temporal-comparison.v1.md"
PROMPT_VERSION = "temporal-comparison-v1"
CONTRACT_VERSION = "temporal-comparison-response-v1"


@lru_cache
def comparison_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache
def comparison_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _validate_result(
    value: Any, first_image_id: str, second_image_id: str
) -> dict[str, Any]:
    expected = {
        "status",
        "equipment_type",
        "region",
        "first_image_id",
        "second_image_id",
        "description",
        "confidence",
        "limitations",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ContractError("Comparison response has missing or unexpected fields")
    if value["status"] not in {"changed", "unchanged", "unknown"}:
        raise ContractError("Comparison status is unknown")
    if value["first_image_id"] != first_image_id:
        raise ContractError("Comparison response references another first image")
    if value["second_image_id"] != second_image_id:
        raise ContractError("Comparison response references another second image")
    if not isinstance(value["equipment_type"], str) or not value["equipment_type"].strip():
        raise ContractError("Comparison equipment_type must be a non-empty string")
    if not isinstance(value["description"], str) or not value["description"].strip():
        raise ContractError("Comparison description must be a non-empty string")
    confidence = value["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ContractError("Comparison confidence must be a number")
    if not 0 <= float(confidence) <= 1:
        raise ContractError("Comparison confidence must be from 0 to 1")
    region = value["region"]
    if not isinstance(region, dict) or set(region) != {"x", "y", "width", "height"}:
        raise ContractError("Comparison region has an invalid shape")
    for key, number in region.items():
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ContractError(f"Comparison region.{key} must be a number")
        if not 0 <= float(number) <= 1:
            raise ContractError(f"Comparison region.{key} must be from 0 to 1")
    if float(region["x"]) + float(region["width"]) > 1.000001:
        raise ContractError("Comparison region exceeds image width")
    if float(region["y"]) + float(region["height"]) > 1.000001:
        raise ContractError("Comparison region exceeds image height")
    if not isinstance(value["limitations"], list) or not all(
        isinstance(item, str) and item.strip() for item in value["limitations"]
    ):
        raise ContractError("Comparison limitations must contain non-empty strings")
    return value


def build_comparison_context(
    object_item: ConstructionObject,
    camera: Camera,
    first_image: SnapshotImage,
    second_image: SnapshotImage,
    first_snapshot: Snapshot,
    second_snapshot: Snapshot,
    storage: Any,
) -> dict[str, Any]:
    return {
        "fixture_version": f"comparison-{first_image.id}-{second_image.id}",
        "contract_version": CONTRACT_VERSION,
        "prompt_version": PROMPT_VERSION,
        "catalog_version": "temporal-comparison-v1",
        "object": {
            "id": object_item.id,
            "name": object_item.name,
            "object_type": object_item.object_type,
            "timezone": object_item.timezone,
            "first_observed_at": first_snapshot.observed_at.isoformat(),
            "second_observed_at": second_snapshot.observed_at.isoformat(),
        },
        "cameras": [
            {
                "camera_id": camera.id,
                "camera_code": camera.code,
                "name": first_image.camera_name_snapshot,
                "zone": first_image.camera_zone_snapshot,
                "view_description": (camera.passport or {}).get("view_description", ""),
                "coverage": (camera.passport or {}).get("coverage", []),
                "fov_revision": first_image.fov_revision,
            }
        ],
        "plan_items": [],
        "images": [
            {
                "image_id": first_image.id,
                "camera_id": camera.id,
                "sha256": first_image.sha256,
                "media_type": first_image.content_type,
                "content": storage.get(first_image.storage_key),
            },
            {
                "image_id": second_image.id,
                "camera_id": camera.id,
                "sha256": second_image.sha256,
                "media_type": second_image.content_type,
                "content": storage.get(second_image.storage_key),
            },
        ],
    }


def run_comparison(
    db: Session,
    storage: Any,
    settings: Settings,
    comparison: TemporalComparison,
    object_item: ConstructionObject,
    camera: Camera,
    first_image: SnapshotImage,
    second_image: SnapshotImage,
    first_snapshot: Snapshot,
    second_snapshot: Snapshot,
) -> None:
    context = build_comparison_context(
        object_item,
        camera,
        first_image,
        second_image,
        first_snapshot,
        second_snapshot,
        storage,
    )
    for config in attempt_plan(settings):
        comparison.provider = config.provider
        comparison.model = config.model
        comparison.raw_response = None
        comparison.result = None
        comparison.error_code = None
        comparison.error_detail = None
        try:
            payload = build_request_payload(
                config, context, comparison_schema(), comparison_prompt()
            )
            raw, headers, duration_ms = call_provider(config, payload)
            comparison.raw_response = raw
            metrics = usage_metrics(
                raw,
                config,
                duration_ms,
                headers.get("x-request-id") or str(raw.get("id", "")),
            )
            comparison.request_id = metrics["request_id"] or None
            comparison.duration_ms = metrics["duration_ms"]
            comparison.input_tokens = metrics["input_tokens"]
            comparison.output_tokens = metrics["output_tokens"]
            comparison.estimated_cost = (
                str(metrics["estimated_cost"])
                if metrics["estimated_cost"] is not None
                else None
            )
            normalized = extract_normalized_response(raw, config.api_style)
            comparison.result = _validate_result(
                normalized, first_image.id, second_image.id
            )
            comparison.state = "completed"
            break
        except ContractError as exc:
            comparison.state = "error"
            comparison.error_code = "invalid_model_response"
            comparison.error_detail = str(exc)
        except ProviderError as exc:
            comparison.state = "error"
            comparison.error_code = "provider_error"
            comparison.error_detail = str(exc)
        except Exception as exc:
            comparison.state = "error"
            comparison.error_code = "internal_error"
            comparison.error_detail = f"{type(exc).__name__}: {exc}"
            break
    comparison.finished_at = datetime.utcnow()
    db.commit()
