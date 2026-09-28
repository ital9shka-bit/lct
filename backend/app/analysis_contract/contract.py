from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set


class ContractError(ValueError):
    """Raised when an input fixture or normalized model answer is invalid."""


def load_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"Expected a JSON object in {path}")
    return value


def _expect_object(value: Any, path: str, keys: Iterable[str]) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{path}: expected object")
    expected = set(keys)
    actual = set(value)
    missing = expected - actual
    extra = actual - expected
    if missing:
        raise ContractError(f"{path}: missing keys {sorted(missing)}")
    if extra:
        raise ContractError(f"{path}: unexpected keys {sorted(extra)}")
    return value


def _expect_list(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{path}: expected array")
    return value


def _expect_string(value: Any, path: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ContractError(f"{path}: expected non-empty string")
    return value


def _expect_integer(value: Any, path: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractError(f"{path}: expected integer >= {minimum}")
    return value


def _expect_confidence(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{path}: expected number from 0 to 1")
    number = float(value)
    if not 0 <= number <= 1:
        raise ContractError(f"{path}: expected number from 0 to 1")
    return number


def _expect_enum(value: Any, path: str, allowed: Set[str]) -> str:
    string = _expect_string(value, path)
    if string not in allowed:
        raise ContractError(f"{path}: expected one of {sorted(allowed)}, got {string!r}")
    return string


def _expect_string_list(value: Any, path: str) -> List[str]:
    return [
        _expect_string(item, f"{path}[{index}]")
        for index, item in enumerate(_expect_list(value, path))
    ]


def _ensure_unique(values: Sequence[str], path: str) -> None:
    duplicates = sorted({item for item in values if values.count(item) > 1})
    if duplicates:
        raise ContractError(f"{path}: duplicate values {duplicates}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_analysis_context(fixture: Mapping[str, Any], project_root: Path) -> Dict[str, Any]:
    fixture_path_keys = {
        "fixture_version",
        "catalog_path",
        "contract_version",
        "prompt_version",
        "object",
        "cameras",
        "plan_items",
        "images",
    }
    _expect_object(fixture, "fixture", fixture_path_keys)
    catalog_path = project_root / _expect_string(fixture["catalog_path"], "catalog_path")
    catalog = load_json(catalog_path)
    _expect_object(catalog, "catalog", {"catalog_version", "object_types", "stages"})

    object_data = _expect_object(
        fixture["object"],
        "object",
        {"id", "name", "object_type", "timezone", "observed_at"},
    )
    object_type = _expect_string(object_data["object_type"], "object.object_type")
    object_type_codes = {
        _expect_string(item.get("code"), f"catalog.object_types[{index}].code")
        for index, item in enumerate(_expect_list(catalog["object_types"], "catalog.object_types"))
        if isinstance(item, dict)
    }
    if object_type not in object_type_codes:
        raise ContractError(f"object.object_type: unknown code {object_type!r}")

    cameras = _expect_list(fixture["cameras"], "cameras")
    camera_ids: List[str] = []
    normalized_cameras: List[Dict[str, Any]] = []
    for index, camera in enumerate(cameras):
        item = _expect_object(
            camera,
            f"cameras[{index}]",
            {"camera_id", "name", "zone", "view_description", "coverage"},
        )
        camera_id = _expect_string(item["camera_id"], f"cameras[{index}].camera_id")
        camera_ids.append(camera_id)
        normalized_cameras.append(dict(item))
        _expect_string_list(item["coverage"], f"cameras[{index}].coverage")
    _ensure_unique(camera_ids, "cameras.camera_id")

    stages_by_code: Dict[str, Mapping[str, Any]] = {}
    for index, stage in enumerate(_expect_list(catalog["stages"], "catalog.stages")):
        if not isinstance(stage, dict):
            raise ContractError(f"catalog.stages[{index}]: expected object")
        code = _expect_string(stage.get("code"), f"catalog.stages[{index}].code")
        stages_by_code[code] = stage

    plan_items = _expect_list(fixture["plan_items"], "plan_items")
    normalized_plan: List[Dict[str, Any]] = []
    plan_ids: List[str] = []
    for index, plan_item in enumerate(plan_items):
        item = _expect_object(
            plan_item,
            f"plan_items[{index}]",
            {"plan_item_id", "stage_code", "start_date", "end_date", "camera_ids"},
        )
        plan_item_id = _expect_string(item["plan_item_id"], f"plan_items[{index}].plan_item_id")
        stage_code = _expect_string(item["stage_code"], f"plan_items[{index}].stage_code")
        if stage_code not in stages_by_code:
            raise ContractError(f"plan_items[{index}].stage_code: unknown code {stage_code!r}")
        stage = stages_by_code[stage_code]
        if object_type not in stage.get("object_types", []):
            raise ContractError(
                f"plan_items[{index}]: stage {stage_code!r} is not applicable to {object_type!r}"
            )
        linked_cameras = _expect_string_list(item["camera_ids"], f"plan_items[{index}].camera_ids")
        unknown_cameras = set(linked_cameras) - set(camera_ids)
        if unknown_cameras:
            raise ContractError(
                f"plan_items[{index}].camera_ids: unknown cameras {sorted(unknown_cameras)}"
            )
        plan_ids.append(plan_item_id)
        normalized_plan.append(
            {
                **dict(item),
                "stage_name": stage["name"],
                "observability": stage["observability"],
                "confirmation_method": stage["confirmation_method"],
                "visual_class": stage["visual_class"],
                "profile": stage["profile"],
            }
        )
    _ensure_unique(plan_ids, "plan_items.plan_item_id")

    images = _expect_list(fixture["images"], "images")
    normalized_images: List[Dict[str, Any]] = []
    image_ids: List[str] = []
    for index, image in enumerate(images):
        item = _expect_object(
            image,
            f"images[{index}]",
            {"image_id", "camera_id", "path", "media_type", "sha256"},
        )
        image_id = _expect_string(item["image_id"], f"images[{index}].image_id")
        camera_id = _expect_string(item["camera_id"], f"images[{index}].camera_id")
        if camera_id not in camera_ids:
            raise ContractError(f"images[{index}].camera_id: unknown camera {camera_id!r}")
        relative_path = _expect_string(item["path"], f"images[{index}].path")
        image_path = (project_root / relative_path).resolve()
        try:
            image_path.relative_to(project_root.resolve())
        except ValueError as exc:
            raise ContractError(f"images[{index}].path escapes the project root") from exc
        if not image_path.is_file():
            raise ContractError(f"images[{index}].path does not exist: {relative_path}")
        actual_hash = _sha256(image_path)
        expected_hash = _expect_string(item["sha256"], f"images[{index}].sha256")
        if actual_hash != expected_hash:
            raise ContractError(
                f"images[{index}].sha256 mismatch: expected {expected_hash}, got {actual_hash}"
            )
        image_ids.append(image_id)
        normalized_images.append({**dict(item), "absolute_path": str(image_path)})
    _ensure_unique(image_ids, "images.image_id")

    return {
        "fixture_version": fixture["fixture_version"],
        "contract_version": fixture["contract_version"],
        "prompt_version": fixture["prompt_version"],
        "catalog_version": catalog["catalog_version"],
        "object": dict(object_data),
        "cameras": normalized_cameras,
        "plan_items": normalized_plan,
        "images": normalized_images,
    }


def _validate_equipment(item: Any, path: str) -> None:
    value = _expect_object(item, path, {"type", "count", "confidence", "description"})
    _expect_string(value["type"], f"{path}.type")
    _expect_integer(value["count"], f"{path}.count", 1)
    _expect_confidence(value["confidence"], f"{path}.confidence")
    _expect_string(value["description"], f"{path}.description")


def _validate_scene_fact(item: Any, path: str) -> None:
    value = _expect_object(item, path, {"feature_code", "state", "confidence", "description"})
    _expect_string(value["feature_code"], f"{path}.feature_code")
    _expect_enum(value["state"], f"{path}.state", {"present", "absent", "uncertain"})
    _expect_confidence(value["confidence"], f"{path}.confidence")
    _expect_string(value["description"], f"{path}.description")


def _profile_feature_codes(plan_item: Mapping[str, Any]) -> Set[str]:
    profile = plan_item.get("profile")
    if not isinstance(profile, dict):
        return set()
    result: Set[str] = set()
    for group in ("strong_features", "additional_features"):
        for feature in profile.get(group, []):
            if isinstance(feature, dict) and isinstance(feature.get("code"), str):
                result.add(feature["code"])
    return result


def validate_analysis(data: Any, context: Mapping[str, Any]) -> Dict[str, Any]:
    top = _expect_object(
        data,
        "analysis",
        {
            "camera_observations",
            "stage_evidence",
            "evidence_items",
            "unexpected_evidence",
            "analysis_summary",
        },
    )
    camera_ids = {item["camera_id"] for item in context["cameras"]}
    image_to_camera = {item["image_id"]: item["camera_id"] for item in context["images"]}
    plan_by_id = {item["plan_item_id"]: item for item in context["plan_items"]}

    observed_images: List[str] = []
    for index, observation in enumerate(
        _expect_list(top["camera_observations"], "analysis.camera_observations")
    ):
        path = f"analysis.camera_observations[{index}]"
        item = _expect_object(
            observation,
            path,
            {"camera_id", "image_id", "quality", "limitations", "equipment", "scene_facts"},
        )
        camera_id = _expect_string(item["camera_id"], f"{path}.camera_id")
        image_id = _expect_string(item["image_id"], f"{path}.image_id")
        if camera_id not in camera_ids:
            raise ContractError(f"{path}.camera_id: unknown camera {camera_id!r}")
        if image_to_camera.get(image_id) != camera_id:
            raise ContractError(f"{path}: image {image_id!r} does not belong to camera {camera_id!r}")
        _expect_enum(item["quality"], f"{path}.quality", {"good", "acceptable", "poor", "unreadable"})
        _expect_string_list(item["limitations"], f"{path}.limitations")
        for equipment_index, equipment in enumerate(_expect_list(item["equipment"], f"{path}.equipment")):
            _validate_equipment(equipment, f"{path}.equipment[{equipment_index}]")
        for fact_index, fact in enumerate(_expect_list(item["scene_facts"], f"{path}.scene_facts")):
            _validate_scene_fact(fact, f"{path}.scene_facts[{fact_index}]")
        observed_images.append(image_id)
    _ensure_unique(observed_images, "analysis.camera_observations.image_id")
    if set(observed_images) != set(image_to_camera):
        missing = sorted(set(image_to_camera) - set(observed_images))
        extra = sorted(set(observed_images) - set(image_to_camera))
        raise ContractError(
            f"analysis.camera_observations must cover each input image once; missing={missing}, extra={extra}"
        )

    evidence_by_id: Dict[str, Mapping[str, Any]] = {}
    for index, evidence in enumerate(_expect_list(top["evidence_items"], "analysis.evidence_items")):
        path = f"analysis.evidence_items[{index}]"
        item = _expect_object(
            evidence,
            path,
            {
                "evidence_id",
                "plan_item_id",
                "feature_code",
                "camera_id",
                "image_id",
                "polarity",
                "confidence",
                "description",
            },
        )
        evidence_id = _expect_string(item["evidence_id"], f"{path}.evidence_id")
        if evidence_id in evidence_by_id:
            raise ContractError(f"{path}.evidence_id: duplicate {evidence_id!r}")
        plan_item_id = _expect_string(item["plan_item_id"], f"{path}.plan_item_id")
        plan_item = plan_by_id.get(plan_item_id)
        if plan_item is None:
            raise ContractError(f"{path}.plan_item_id: unknown plan item {plan_item_id!r}")
        feature_code = _expect_string(item["feature_code"], f"{path}.feature_code")
        if feature_code not in _profile_feature_codes(plan_item):
            raise ContractError(
                f"{path}.feature_code: {feature_code!r} is not in the profile for {plan_item_id!r}"
            )
        camera_id = _expect_string(item["camera_id"], f"{path}.camera_id")
        image_id = _expect_string(item["image_id"], f"{path}.image_id")
        if image_to_camera.get(image_id) != camera_id:
            raise ContractError(f"{path}: image {image_id!r} does not belong to camera {camera_id!r}")
        if camera_id not in plan_item["camera_ids"]:
            raise ContractError(f"{path}: camera {camera_id!r} is not linked to plan item {plan_item_id!r}")
        _expect_enum(item["polarity"], f"{path}.polarity", {"positive", "neutral", "conflict"})
        _expect_confidence(item["confidence"], f"{path}.confidence")
        _expect_string(item["description"], f"{path}.description")
        evidence_by_id[evidence_id] = item

    seen_plan_items: List[str] = []
    for index, stage in enumerate(_expect_list(top["stage_evidence"], "analysis.stage_evidence")):
        path = f"analysis.stage_evidence[{index}]"
        item = _expect_object(
            stage,
            path,
            {"plan_item_id", "status", "confidence", "evidence_item_ids", "explanation", "limitations"},
        )
        plan_item_id = _expect_string(item["plan_item_id"], f"{path}.plan_item_id")
        plan_item = plan_by_id.get(plan_item_id)
        if plan_item is None:
            raise ContractError(f"{path}.plan_item_id: unknown plan item {plan_item_id!r}")
        status = _expect_enum(
            item["status"],
            f"{path}.status",
            {"positive", "neutral", "conflict", "not_observable", "insufficient_coverage"},
        )
        is_not_observable = (
            plan_item["confirmation_method"] == "inspection" or plan_item["observability"] == "no"
        )
        if status == "not_observable" and not is_not_observable:
            raise ContractError(f"{path}.status: model cannot mark a camera-confirmed stage not_observable")
        if is_not_observable and status != "not_observable":
            raise ContractError(f"{path}.status: inspection-only stage must be not_observable")
        _expect_confidence(item["confidence"], f"{path}.confidence")
        evidence_ids = _expect_string_list(item["evidence_item_ids"], f"{path}.evidence_item_ids")
        _ensure_unique(evidence_ids, f"{path}.evidence_item_ids")
        linked = []
        for evidence_id in evidence_ids:
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                raise ContractError(f"{path}.evidence_item_ids: unknown evidence {evidence_id!r}")
            if evidence["plan_item_id"] != plan_item_id:
                raise ContractError(f"{path}.evidence_item_ids: evidence {evidence_id!r} belongs to another stage")
            linked.append(evidence)
        if status == "positive" and not any(e["polarity"] == "positive" for e in linked):
            raise ContractError(f"{path}: positive status needs positive evidence")
        if status == "conflict" and not any(e["polarity"] == "conflict" for e in linked):
            raise ContractError(f"{path}: conflict status needs conflict evidence")
        if status == "not_observable" and evidence_ids:
            raise ContractError(f"{path}: not_observable stage cannot cite camera evidence")
        _expect_string(item["explanation"], f"{path}.explanation")
        _expect_string_list(item["limitations"], f"{path}.limitations")
        seen_plan_items.append(plan_item_id)
    _ensure_unique(seen_plan_items, "analysis.stage_evidence.plan_item_id")
    if set(seen_plan_items) != set(plan_by_id):
        raise ContractError("analysis.stage_evidence must contain every active plan item exactly once")

    active_feature_codes = set().union(*(_profile_feature_codes(item) for item in plan_by_id.values()))
    for index, unexpected in enumerate(
        _expect_list(top["unexpected_evidence"], "analysis.unexpected_evidence")
    ):
        path = f"analysis.unexpected_evidence[{index}]"
        item = _expect_object(
            unexpected,
            path,
            {"feature_code", "camera_id", "image_id", "confidence", "description"},
        )
        feature_code = _expect_string(item["feature_code"], f"{path}.feature_code")
        if feature_code in active_feature_codes:
            raise ContractError(f"{path}.feature_code belongs to an active stage and is not unexpected")
        camera_id = _expect_string(item["camera_id"], f"{path}.camera_id")
        image_id = _expect_string(item["image_id"], f"{path}.image_id")
        if image_to_camera.get(image_id) != camera_id:
            raise ContractError(f"{path}: image {image_id!r} does not belong to camera {camera_id!r}")
        _expect_confidence(item["confidence"], f"{path}.confidence")
        _expect_string(item["description"], f"{path}.description")

    _expect_string(top["analysis_summary"], "analysis.analysis_summary")
    return dict(top)
