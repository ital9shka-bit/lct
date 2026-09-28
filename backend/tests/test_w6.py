from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.models import Snapshot, TemporalComparison
from backend.tests.test_w1 import register
from backend.tests.test_w3 import (
    MemoryStorage,
    app_with_storage,
    create_ready_object,
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


def create_image(
    client: TestClient,
    object_item: dict,
    observed_time: str,
    camera_index: int = 0,
    *,
    png: bool = False,
    observed_date: str = "2026-09-19",
) -> dict:
    snapshot = client.post(
        f"/objects/{object_item['id']}/snapshots",
        json={"observed_date": observed_date, "observed_time": observed_time},
    ).json()
    uploaded = upload_image(
        client,
        snapshot["id"],
        object_item["cameras"][camera_index]["id"],
        body=image_bytes("PNG" if png else "JPEG"),
        filename="camera.png" if png else "camera.jpg",
        media_type="image/png" if png else "image/jpeg",
    )
    assert uploaded.status_code == 201, uploaded.text
    with client.app.state.session_factory() as db:
        stored_snapshot = db.get(Snapshot, snapshot["id"])
        stored_snapshot.state = "completed"
        db.commit()
    return uploaded.json()


def test_temporal_comparison_is_validated_persisted_and_idempotent(
    engine, monkeypatch
) -> None:
    storage = MemoryStorage()
    calls = []

    def fake_provider(config, payload):
        calls.append(payload)
        context = public_context(payload)
        first, second = context["images"]
        result = {
            "status": "unchanged",
            "equipment_type": "excavator",
            "region": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2},
            "first_image_id": first["image_id"],
            "second_image_id": second["image_id"],
            "description": "Экскаватор остаётся в той же области кадра.",
            "confidence": 0.88,
            "limitations": ["Сравниваются только два контрольных момента."],
        }
        return (
            {
                "id": "comparison-request",
                "choices": [{"message": {"content": json.dumps(result)}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 60},
            },
            {"x-request-id": "comparison-request"},
            250,
        )

    monkeypatch.setattr("backend.app.temporal.call_provider", fake_provider)
    with TestClient(app_with_storage(engine, storage)) as client:
        register(client, "w6-compare@example.org")
        object_item = create_ready_object(client)
        first = create_image(client, object_item, "09:00")
        second = create_image(client, object_item, "12:00", png=True)
        response = client.post(
            f"/objects/{object_item['id']}/comparisons",
            json={
                "first_image_id": second["id"],
                "second_image_id": first["id"],
            },
        )
        assert response.status_code == 201, response.text
        comparison = response.json()
        assert comparison["state"] == "completed"
        assert comparison["result"]["status"] == "unchanged"
        assert comparison["first_image"]["id"] == first["id"]
        assert comparison["second_image"]["id"] == second["id"]
        repeated = client.post(
            f"/objects/{object_item['id']}/comparisons",
            json={"first_image_id": first["id"], "second_image_id": second["id"]},
        )
        assert repeated.json()["id"] == comparison["id"]
        assert len(calls) == 1
        assert len(client.get(f"/objects/{object_item['id']}/comparisons").json()) == 1


def test_comparison_rejects_other_camera_and_changed_fov(engine) -> None:
    storage = MemoryStorage()
    with TestClient(app_with_storage(engine, storage)) as client:
        register(client, "w6-guard@example.org")
        object_item = create_ready_object(client)
        first = create_image(client, object_item, "09:00")
        other_camera = create_image(client, object_item, "12:00", camera_index=1, png=True)
        mismatch = client.post(
            f"/objects/{object_item['id']}/comparisons",
            json={
                "first_image_id": first["id"],
                "second_image_id": other_camera["id"],
            },
        )
        assert mismatch.status_code == 422

        changed = client.post(
            f"/cameras/{object_item['cameras'][0]['id']}/fov-revision"
        )
        assert changed.status_code == 200
        second = create_image(client, object_item, "15:00", png=True)
        changed_fov = client.post(
            f"/objects/{object_item['id']}/comparisons",
            json={"first_image_id": first["id"], "second_image_id": second["id"]},
        )
        assert changed_fov.status_code == 422


def test_three_day_unchanged_chain_creates_movement_signal_and_change_breaks_it(
    engine,
) -> None:
    storage = MemoryStorage()
    app = app_with_storage(engine, storage)
    with TestClient(app) as client:
        register(client, "w6-movement@example.org")
        object_item = create_ready_object(client)
        images = []
        for observed_date in ["2026-09-17", "2026-09-18", "2026-09-19"]:
            images.append(
                create_image(
                    client,
                    object_item,
                    "09:00",
                    observed_date=observed_date,
                )
            )
            images.append(
                create_image(
                    client,
                    object_item,
                    "12:00",
                    png=True,
                    observed_date=observed_date,
                )
            )
            images.append(
                create_image(
                    client,
                    object_item,
                    "15:00",
                    observed_date=observed_date,
                )
            )

        pairs = list(zip(images, images[1:]))
        with app.state.session_factory() as db:
            comparisons = []
            for first, second in pairs:
                item = TemporalComparison(
                    object_id=object_item["id"],
                    camera_id=object_item["cameras"][0]["id"],
                    first_image_id=first["id"],
                    second_image_id=second["id"],
                    state="completed",
                    provider="test",
                    model="test",
                    prompt_version="temporal-comparison-v1",
                    result={
                        "status": "unchanged",
                        "equipment_type": "excavator",
                        "region": {
                            "x": 0.2,
                            "y": 0.3,
                            "width": 0.2,
                            "height": 0.2,
                        },
                        "first_image_id": first["id"],
                        "second_image_id": second["id"],
                        "description": "Положение не изменилось.",
                        "confidence": 0.9,
                        "limitations": [],
                    },
                )
                db.add(item)
                comparisons.append(item)
            db.commit()
            overnight_id = comparisons[2].id
            broken_id = comparisons[3].id

        movement = client.get(
            f"/objects/{object_item['id']}/movement",
            params={"date": "2026-09-19"},
        )
        assert movement.status_code == 200, movement.text
        signal = movement.json()["signals"][0]
        assert signal["idle_days"] == 3
        assert signal["observation_count"] == 9
        assert len(signal["comparison_ids"]) == 6
        assert overnight_id not in signal["comparison_ids"]
        assert signal["equipment_type"] == "excavator"

        # Модель может назвать тот же экскаватор более подробно в одном интервале.
        with app.state.session_factory() as db:
            renamed = db.get(TemporalComparison, comparisons[4].id)
            renamed.result = {**renamed.result, "equipment_type": "гусеничный экскаватор"}
            db.commit()
        assert (
            client.get(
                f"/objects/{object_item['id']}/movement",
                params={"date": "2026-09-19"},
            ).json()["signals"][0]["idle_days"]
            == 3
        )

        # Смена класса техники должна разорвать последовательность.
        with app.state.session_factory() as db:
            renamed = db.get(TemporalComparison, comparisons[4].id)
            renamed.result = {**renamed.result, "equipment_type": "самосвал"}
            db.commit()
        assert client.get(
            f"/objects/{object_item['id']}/movement",
            params={"date": "2026-09-19"},
        ).json()["signals"] == []
        with app.state.session_factory() as db:
            renamed = db.get(TemporalComparison, comparisons[4].id)
            renamed.result = {**renamed.result, "equipment_type": "excavator"}
            db.commit()

        # Ночная пара не влияет: утром техника может стоять на стоянке или в новом месте.
        with app.state.session_factory() as db:
            overnight = db.get(TemporalComparison, overnight_id)
            overnight.result = {**overnight.result, "status": "changed"}
            db.commit()
        assert (
            client.get(
                f"/objects/{object_item['id']}/movement",
                params={"date": "2026-09-19"},
            ).json()["signals"][0]["idle_days"]
            == 3
        )

        with app.state.session_factory() as db:
            broken = db.get(TemporalComparison, broken_id)
            broken.result = {**broken.result, "status": "changed"}
            db.commit()
        assert (
            client.get(
                f"/objects/{object_item['id']}/movement",
                params={"date": "2026-09-19"},
            ).json()["signals"]
            == []
        )
