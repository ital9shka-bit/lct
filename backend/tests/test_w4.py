from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.models import DayEvaluation
from backend.tests.test_w1 import register
from backend.tests.test_w2 import create_payload, stage
from backend.tests.test_w3 import (
    MemoryStorage,
    app_with_storage,
    image_bytes,
    public_context,
    upload_image,
)


@pytest.fixture
def engine():
    value = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(value)
    return value


def create_object(client: TestClient, *, with_hidden: bool = False) -> dict:
    payload = create_payload()
    if with_hidden:
        hidden = stage("Внутренние инженерные сети", "stage-hidden")
        hidden.update(
            {
                "confirmation_method": "inspection",
                "observability": "no",
                "camera_ids": [],
            }
        )
        payload["plan_items"].append(hidden)
    response = client.post("/objects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def model_result(context: dict, *, positive: bool, confidence: float = 0.95) -> dict:
    observations = [
        {
            "camera_id": image["camera_id"],
            "image_id": image["image_id"],
            "quality": "good",
            "limitations": [],
            "equipment": [],
            "scene_facts": [],
        }
        for image in context["images"]
    ]
    stages = []
    evidence = []
    for plan_item in context["plan_items"]:
        if plan_item["confirmation_method"] == "inspection" or plan_item["observability"] == "no":
            stages.append(
                {
                    "plan_item_id": plan_item["plan_item_id"],
                    "status": "not_observable",
                    "confidence": 1,
                    "evidence_item_ids": [],
                    "explanation": "Этап подтверждается осмотром.",
                    "limitations": [],
                }
            )
            continue
        evidence_ids = []
        if positive:
            image = context["images"][0]
            feature = plan_item["profile"]["strong_features"][0]["code"]
            evidence_id = f"ev-{image['image_id']}"
            evidence_ids.append(evidence_id)
            evidence.append(
                {
                    "evidence_id": evidence_id,
                    "plan_item_id": plan_item["plan_item_id"],
                    "feature_code": feature,
                    "camera_id": image["camera_id"],
                    "image_id": image["image_id"],
                    "polarity": "positive",
                    "confidence": confidence,
                    "description": "Сильный признак этапа виден в кадре.",
                }
            )
        stages.append(
            {
                "plan_item_id": plan_item["plan_item_id"],
                "status": "positive" if positive else "neutral",
                "confidence": confidence,
                "evidence_item_ids": evidence_ids,
                "explanation": "Признак найден." if positive else "Признак не найден.",
                "limitations": [],
            }
        )
    return {
        "camera_observations": observations,
        "stage_evidence": stages,
        "evidence_items": evidence,
        "unexpected_evidence": [],
        "analysis_summary": "Готово.",
    }


def provider(*, positive: bool, confidence: float = 0.95):
    def call(config, payload):
        result = model_result(
            public_context(payload), positive=positive, confidence=confidence
        )
        return (
            {
                "id": "w4-request",
                "choices": [{"message": {"content": json.dumps(result)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            },
            {},
            50,
        )

    return call


def add_check(
    client: TestClient,
    object_item: dict,
    observed_time: str,
    *,
    body: bytes | None = None,
) -> dict:
    created = client.post(
        f"/objects/{object_item['id']}/snapshots",
        json={"observed_date": "2026-09-19", "observed_time": observed_time},
    )
    assert created.status_code == 201, created.text
    snapshot = created.json()
    uploaded = upload_image(
        client,
        snapshot["id"],
        object_item["cameras"][0]["id"],
        body=body,
    )
    assert uploaded.status_code == 201, uploaded.text
    analyzed = client.post(f"/snapshots/{snapshot['id']}/analyze")
    assert analyzed.status_code == 202, analyzed.text
    return client.get(f"/snapshots/{snapshot['id']}").json()


def test_snapshot_is_bound_to_nearest_slot_with_earlier_tie(engine) -> None:
    storage = MemoryStorage()
    with TestClient(app_with_storage(engine, storage)) as client:
        register(client, "w4-slot@example.org")
        object_item = create_object(client)
        response = client.post(
            f"/objects/{object_item['id']}/snapshots",
            json={"observed_date": "2026-09-19", "observed_time": "10:30"},
        )
        assert response.status_code == 201
        assert response.json()["control_slot"] == "09:00"


def test_object_local_date_is_not_shifted_by_timezone(engine, monkeypatch) -> None:
    storage = MemoryStorage()
    monkeypatch.setattr("backend.app.analysis.call_provider", provider(positive=True))
    with TestClient(app_with_storage(engine, storage)) as client:
        register(client, "w4-timezone@example.org")
        payload = create_payload()
        payload["timezone"] = "Asia/Yekaterinburg"
        object_item = client.post("/objects", json=payload).json()
        snapshot = add_check(client, object_item, "18:40", body=image_bytes())
        assert snapshot["observed_at"].startswith("2026-09-19")
        report = client.get(f"/objects/{object_item['id']}/days/2026-09-19").json()
        assert report["date"] == "2026-09-19"
        assert report["received"] == 1


def test_two_unique_positive_intervals_confirm_stage(engine, monkeypatch) -> None:
    storage = MemoryStorage()
    monkeypatch.setattr("backend.app.analysis.call_provider", provider(positive=True))
    app = app_with_storage(engine, storage)
    with TestClient(app) as client:
        register(client, "w4-positive@example.org")
        object_item = create_object(client)
        add_check(client, object_item, "09:00", body=image_bytes())
        second = image_bytes("PNG")
        add_check(client, object_item, "12:00", body=second)

        report = client.get(f"/objects/{object_item['id']}/days/2026-09-19")
        assert report.status_code == 200, report.text
        stage_result = report.json()["stages"][0]
        assert stage_result["status"] == "confirmed"
        assert stage_result["positive_intervals"] == 2
        assert report.json()["received"] == 2
        with app.state.session_factory() as db:
            saved = db.scalar(select(DayEvaluation))
            assert saved.rules_version == "day-rules-v1"
            assert saved.schedule_snapshot["version"] == 1


def test_repeated_positive_image_hash_does_not_add_confirmation(engine, monkeypatch) -> None:
    storage = MemoryStorage()
    monkeypatch.setattr("backend.app.analysis.call_provider", provider(positive=True))
    with TestClient(app_with_storage(engine, storage)) as client:
        register(client, "w4-duplicate@example.org")
        object_item = create_object(client)
        repeated = image_bytes()
        add_check(client, object_item, "09:00", body=repeated)
        add_check(client, object_item, "12:00", body=repeated)
        report = client.get(f"/objects/{object_item['id']}/days/2026-09-19").json()
        stage_result = report["stages"][0]
        assert stage_result["status"] == "insufficient_data"
        assert stage_result["positive_intervals"] == 1
        assert stage_result["cells"][1]["independent"] is False


def test_latest_successful_check_wins_inside_control_slot(engine, monkeypatch) -> None:
    storage = MemoryStorage()
    outcomes = iter([True, False])

    def changing_provider(config, payload):
        result = model_result(
            public_context(payload), positive=next(outcomes), confidence=0.95
        )
        return (
            {
                "id": "w4-latest",
                "choices": [{"message": {"content": json.dumps(result)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            },
            {},
            50,
        )

    monkeypatch.setattr("backend.app.analysis.call_provider", changing_provider)
    with TestClient(app_with_storage(engine, storage)) as client:
        register(client, "w4-latest@example.org")
        object_item = create_object(client)
        add_check(client, object_item, "09:00", body=image_bytes())
        add_check(client, object_item, "09:20", body=image_bytes("PNG"))
        report = client.get(f"/objects/{object_item['id']}/days/2026-09-19").json()
        stage_result = report["stages"][0]
        assert report["received"] == 1
        assert stage_result["positive_intervals"] == 0
        assert stage_result["usable_intervals"] == 1
        assert stage_result["cells"][0]["state"] == "none"


def test_three_high_confidence_absences_create_possible_deviation(engine, monkeypatch) -> None:
    storage = MemoryStorage()
    monkeypatch.setattr(
        "backend.app.analysis.call_provider",
        provider(positive=False, confidence=0.9),
    )
    with TestClient(app_with_storage(engine, storage)) as client:
        register(client, "w4-absence@example.org")
        object_item = create_object(client)
        add_check(client, object_item, "09:00", body=image_bytes())
        add_check(client, object_item, "12:00", body=image_bytes("PNG"))
        add_check(client, object_item, "15:00", body=image_bytes())
        stage_result = client.get(
            f"/objects/{object_item['id']}/days/2026-09-19"
        ).json()["stages"][0]
        assert stage_result["status"] == "possible_deviation"
        assert stage_result["usable_intervals"] == 3


def test_inspection_overrides_hidden_stage_and_keeps_history(engine) -> None:
    storage = MemoryStorage()
    with TestClient(app_with_storage(engine, storage)) as client:
        register(client, "w4-inspection@example.org")
        object_item = create_object(client, with_hidden=True)
        hidden = next(
            item
            for item in object_item["plan_items"]
            if item["name"] == "Внутренние инженерные сети"
        )
        first = client.post(
            f"/objects/{object_item['id']}/inspections",
            data={
                "plan_item_id": hidden["id"],
                "observed_date": "2026-09-19",
                "valid_until": "2026-09-21",
                "verdict": "confirmed",
                "author": "Инженер Петров",
                "role": "Технадзор",
                "comment": "Работы подтверждены на месте.",
            },
            files={"files": ("proof.png", image_bytes("PNG"), "image/png")},
        )
        assert first.status_code == 201, first.text
        assert first.json()["attachments"][0]["content_type"] == "image/png"
        report = client.get(f"/objects/{object_item['id']}/days/2026-09-20").json()
        hidden_result = next(
            item for item in report["stages"] if item["plan_item_id"] == hidden["id"]
        )
        assert hidden_result["status"] == "inspection_confirmed"
        assert hidden_result["source"]["author"] == "Инженер Петров"

        second = client.post(
            f"/objects/{object_item['id']}/inspections",
            data={
                "plan_item_id": hidden["id"],
                "observed_date": "2026-09-19",
                "valid_until": "2026-09-21",
                "verdict": "note",
                "author": "Инженер Сидорова",
                "comment": "Нужно повторно проверить участок.",
            },
        )
        assert second.status_code == 201, second.text
        history = client.get(f"/objects/{object_item['id']}/inspections").json()
        assert len(history) == 2
        assert history[0]["superseded"] is False
        assert history[1]["superseded"] is True
        updated = client.get(f"/objects/{object_item['id']}/days/2026-09-20").json()
        hidden_result = next(
            item for item in updated["stages"] if item["plan_item_id"] == hidden["id"]
        )
        assert hidden_result["status"] == "inspection_note"


def test_group_is_assessed_once_and_references_children(engine, monkeypatch) -> None:
    storage = MemoryStorage()
    monkeypatch.setattr("backend.app.analysis.call_provider", provider(positive=True))
    with TestClient(app_with_storage(engine, storage)) as client:
        register(client, "w4-group@example.org")
        payload = create_payload()
        payload["plan_items"].append(
            stage("Монтаж башенного крана", "stage-b", ["cam-b"])
        )
        created = client.post("/objects", json=payload).json()
        item_ids = [item["id"] for item in created["plan_items"]]
        grouped = client.post(
            f"/objects/{created['id']}/plan/group",
            json={
                "item_ids": item_ids,
                "name": "Нулевой цикл",
                "confirmation_method": "cameras",
            },
        )
        assert grouped.status_code == 200, grouped.text
        group = grouped.json()[0]
        snapshot = add_check(client, created, "09:00", body=image_bytes())
        frozen_stage = snapshot["plan_snapshot"]["plan_items"][0]
        assert frozen_stage["plan_item_id"] == group["id"]
        assert {item["plan_item_id"] for item in frozen_stage["children"]} == set(
            item_ids
        )
        report = client.get(f"/objects/{created['id']}/days/2026-09-19").json()
        assert len(report["stages"]) == 1
        assert report["stages"][0]["plan_item_id"] == group["id"]
        assert len(report["stages"][0]["children"]) == 2
