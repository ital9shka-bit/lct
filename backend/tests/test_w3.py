from __future__ import annotations

import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from backend.app.analysis_contract.client import ProviderError
from backend.app.database import Base
from backend.app.main import create_app
from backend.app.models import AnalysisAttempt, Snapshot
from backend.app.storage import StoredObject
from backend.tests.test_w1 import ToggleMailSender, make_settings, register
from backend.tests.test_w2 import create_payload


class MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def ensure_ready(self) -> None:
        return None

    def healthcheck(self) -> str:
        return "ok"

    def put(self, key: str, body: bytes, content_type: str) -> StoredObject:
        self.objects[key] = body
        return StoredObject(key=key, etag="memory")

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def presigned_get(self, key: str) -> str:
        return f"https://storage.test/{key}"


@pytest.fixture
def engine():
    value = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(value)
    return value


def image_bytes(format_name: str = "JPEG") -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 24), "#7a8a77").save(output, format=format_name)
    return output.getvalue()


def app_with_storage(engine, storage: MemoryStorage):
    return create_app(
        make_settings(ai_api_key="test-only"),
        engine=engine,
        storage=storage,
        mail_sender=ToggleMailSender(),
    )


def create_ready_object(client: TestClient) -> dict:
    response = client.post("/objects", json=create_payload())
    assert response.status_code == 201, response.text
    return response.json()


def create_snapshot(client: TestClient, object_id: str, observed_time: str = "09:00") -> dict:
    response = client.post(
        f"/objects/{object_id}/snapshots",
        json={
            "observed_date": "2026-09-19",
            "observed_time": observed_time,
            "source": "manual",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload_image(
    client: TestClient,
    snapshot_id: str,
    camera_id: str,
    *,
    body: bytes | None = None,
    filename: str = "camera.jpg",
    media_type: str = "image/jpeg",
):
    return client.post(
        f"/snapshots/{snapshot_id}/images",
        data={"camera_id": camera_id, "source": "manual"},
        files={"file": (filename, body or image_bytes(), media_type)},
    )


def public_context(payload: dict) -> dict:
    content = payload["messages"][1]["content"]
    text = content[0]["text"]
    return json.loads(text.removeprefix("Контекст проверки:\n"))


def valid_analysis(context: dict, *, unreadable: bool = False) -> dict:
    observations = []
    for index, image in enumerate(context["images"]):
        observations.append(
            {
                "camera_id": image["camera_id"],
                "image_id": image["image_id"],
                "quality": "unreadable" if unreadable and index == 0 else "good",
                "limitations": ["Кадр не читается"] if unreadable and index == 0 else [],
                "equipment": [],
                "scene_facts": [],
            }
        )
    stages = []
    for item in context["plan_items"]:
        stages.append(
            {
                "plan_item_id": item["plan_item_id"],
                "status": (
                    "not_observable"
                    if item["confirmation_method"] == "inspection"
                    or item["observability"] == "no"
                    else "neutral"
                ),
                "confidence": 0.4,
                "evidence_item_ids": [],
                "explanation": "Надёжных признаков в доступных кадрах не найдено.",
                "limitations": [],
            }
        )
    return {
        "camera_observations": observations,
        "stage_evidence": stages,
        "evidence_items": [],
        "unexpected_evidence": [],
        "analysis_summary": "Кадры обработаны.",
    }


def provider_response(payload: dict, *, unreadable: bool = False):
    normalized = valid_analysis(public_context(payload), unreadable=unreadable)
    return (
        {
            "id": "request-test",
            "choices": [{"message": {"content": json.dumps(normalized)}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 80},
        },
        {"x-request-id": "request-test"},
        321,
    )


def test_snapshot_upload_replace_delete_and_validation(engine) -> None:
    storage = MemoryStorage()
    with TestClient(app_with_storage(engine, storage)) as client:
        assert register(client, "w3-files@example.org").status_code == 201
        object_item = create_ready_object(client)
        snapshot = create_snapshot(client, object_item["id"])
        camera_id = object_item["cameras"][0]["id"]

        uploaded = upload_image(client, snapshot["id"], camera_id)
        assert uploaded.status_code == 201, uploaded.text
        first = uploaded.json()
        assert first["content_type"] == "image/jpeg"
        assert first["source"] == "manual"

        replacement = upload_image(
            client,
            snapshot["id"],
            camera_id,
            body=image_bytes("PNG"),
            filename="replacement.png",
            media_type="image/png",
        )
        assert replacement.status_code == 201
        assert replacement.json()["id"] == first["id"]
        assert replacement.json()["content_type"] == "image/png"

        invalid = upload_image(
            client,
            snapshot["id"],
            object_item["cameras"][1]["id"],
            body=b"not-an-image",
        )
        assert invalid.status_code == 422

        assert client.delete(f"/snapshot-images/{first['id']}").status_code == 204
        assert client.get(f"/snapshots/{snapshot['id']}").json()["images"] == []
        assert client.delete(f"/snapshots/{snapshot['id']}").status_code == 204
        assert client.get(f"/snapshots/{snapshot['id']}").status_code == 404


def test_duplicate_snapshot_foreign_camera_and_empty_analysis_are_rejected(engine) -> None:
    storage = MemoryStorage()
    app = app_with_storage(engine, storage)
    with TestClient(app) as alice, TestClient(app) as bob:
        assert register(alice, "w3-alice@example.org").status_code == 201
        alice_object = create_ready_object(alice)
        snapshot = create_snapshot(alice, alice_object["id"])
        duplicate = alice.post(
            f"/objects/{alice_object['id']}/snapshots",
            json={"observed_date": "2026-09-19", "observed_time": "09:00"},
        )
        assert duplicate.status_code == 409
        assert alice.post(f"/snapshots/{snapshot['id']}/analyze").status_code == 422

        assert register(bob, "w3-bob@example.org").status_code == 201
        bob_object = create_ready_object(bob)
        forbidden = upload_image(
            bob,
            snapshot["id"],
            bob_object["cameras"][0]["id"],
        )
        assert forbidden.status_code == 404


def test_analysis_is_persisted_and_idempotent(engine, monkeypatch) -> None:
    storage = MemoryStorage()
    calls = []

    def fake_provider(config, payload):
        calls.append(payload)
        return provider_response(payload)

    monkeypatch.setattr("backend.app.analysis.call_provider", fake_provider)
    with TestClient(app_with_storage(engine, storage)) as client:
        assert register(client, "w3-analysis@example.org").status_code == 201
        object_item = create_ready_object(client)
        snapshot = create_snapshot(client, object_item["id"])
        assert upload_image(client, snapshot["id"], object_item["cameras"][0]["id"]).status_code == 201

        first = client.post(
            f"/snapshots/{snapshot['id']}/analyze",
            headers={"Idempotency-Key": "analysis-1"},
        )
        assert first.status_code == 202, first.text
        saved = client.get(f"/snapshots/{snapshot['id']}").json()
        assert saved["state"] == "completed"
        assert saved["attempts"][0]["normalized_response"]["analysis_summary"] == "Кадры обработаны."
        assert saved["attempts"][0]["raw_response"]["id"] == "request-test"
        assert saved["attempts"][0]["duration_ms"] == 321
        assert saved["attempts"][0]["input_tokens"] == 120

        repeated = client.post(
            f"/snapshots/{snapshot['id']}/analyze",
            headers={"Idempotency-Key": "analysis-1"},
        )
        assert repeated.status_code == 202
        assert repeated.json()["attempt_id"] == first.json()["attempt_id"]
        assert len(calls) == 1


def test_unreadable_camera_marks_snapshot_partial(engine, monkeypatch) -> None:
    storage = MemoryStorage()
    monkeypatch.setattr(
        "backend.app.analysis.call_provider",
        lambda config, payload: provider_response(payload, unreadable=True),
    )
    with TestClient(app_with_storage(engine, storage)) as client:
        assert register(client, "w3-partial@example.org").status_code == 201
        object_item = create_ready_object(client)
        snapshot = create_snapshot(client, object_item["id"])
        upload_image(client, snapshot["id"], object_item["cameras"][0]["id"])
        response = client.post(f"/snapshots/{snapshot['id']}/analyze")
        assert response.status_code == 202
        assert client.get(f"/snapshots/{snapshot['id']}").json()["state"] == "partial"


def test_provider_failure_exhausts_primary_and_fallback_without_fixture(engine, monkeypatch) -> None:
    storage = MemoryStorage()
    models: list[str] = []

    def failing_provider(config, payload):
        models.append(config.model)
        raise ProviderError("provider unavailable")

    monkeypatch.setattr("backend.app.analysis.call_provider", failing_provider)
    app = app_with_storage(engine, storage)
    with TestClient(app) as client:
        assert register(client, "w3-failure@example.org").status_code == 201
        object_item = create_ready_object(client)
        snapshot = create_snapshot(client, object_item["id"])
        upload_image(client, snapshot["id"], object_item["cameras"][0]["id"])
        assert client.post(f"/snapshots/{snapshot['id']}/analyze").status_code == 202
        saved = client.get(f"/snapshots/{snapshot['id']}").json()
        primary = "openai/gpt-6-luna"
        fallback = "x-ai/grok-4.7"
        assert models == [primary, primary, fallback, fallback]
        assert saved["state"] == "error"
        assert [item["state"] for item in saved["attempts"]] == ["error"] * 4
        assert [item["model"] for item in saved["attempts"]] == models
        assert all(item["normalized_response"] is None for item in saved["attempts"])

        with app.state.session_factory() as db:
            attempts = db.scalars(
                select(AnalysisAttempt).where(AnalysisAttempt.snapshot_id == snapshot["id"])
            ).all()
            assert sorted(item.attempt_number for item in attempts) == [1, 2, 3, 4]


def test_invalid_model_response_is_retried_then_fallback_answers(engine, monkeypatch) -> None:
    storage = MemoryStorage()
    models: list[str] = []

    def flaky_provider(config, payload):
        models.append(config.model)
        if config.model == "openai/gpt-6-luna":
            return (
                {"id": "invalid", "choices": [{"message": {"content": '{"bad": true}'}}]},
                {},
                100,
            )
        assert "reasoning_effort" not in payload
        return provider_response(payload)

    monkeypatch.setattr("backend.app.analysis.call_provider", flaky_provider)
    with TestClient(app_with_storage(engine, storage)) as client:
        assert register(client, "w3-invalid@example.org").status_code == 201
        object_item = create_ready_object(client)
        snapshot = create_snapshot(client, object_item["id"])
        upload_image(client, snapshot["id"], object_item["cameras"][0]["id"])
        client.post(f"/snapshots/{snapshot['id']}/analyze")
        saved = client.get(f"/snapshots/{snapshot['id']}").json()
        assert models == ["openai/gpt-6-luna", "openai/gpt-6-luna", "x-ai/grok-4.7"]
        assert saved["state"] == "completed"
        attempts = saved["attempts"]
        assert [item["state"] for item in attempts] == ["error", "error", "completed"]
        assert attempts[0]["error_code"] == "invalid_model_response"
        assert attempts[0]["raw_response"]["id"] == "invalid"
        assert attempts[2]["model"] == "x-ai/grok-4.7"
        assert attempts[2]["normalized_response"]["analysis_summary"] == "Кадры обработаны."


def test_fallback_can_be_disabled(engine, monkeypatch) -> None:
    storage = MemoryStorage()
    calls = 0

    def invalid_provider(config, payload):
        nonlocal calls
        calls += 1
        return ({"id": "invalid", "choices": [{"message": {"content": "не JSON"}}]}, {}, 100)

    monkeypatch.setattr("backend.app.analysis.call_provider", invalid_provider)
    app = create_app(
        make_settings(ai_api_key="test-only", ai_fallback_model="", ai_attempts_per_model=1),
        engine=engine,
        storage=storage,
        mail_sender=ToggleMailSender(),
    )
    with TestClient(app) as client:
        assert register(client, "w3-nofallback@example.org").status_code == 201
        object_item = create_ready_object(client)
        snapshot = create_snapshot(client, object_item["id"])
        upload_image(client, snapshot["id"], object_item["cameras"][0]["id"])
        client.post(f"/snapshots/{snapshot['id']}/analyze")
        saved = client.get(f"/snapshots/{snapshot['id']}").json()
        assert calls == 1
        assert saved["state"] == "error"
        assert saved["attempts"][0]["error_code"] == "invalid_model_response"


def test_restart_marks_interrupted_job_as_error(engine) -> None:
    storage = MemoryStorage()
    app = app_with_storage(engine, storage)
    with TestClient(app) as client:
        assert register(client, "w3-restart@example.org").status_code == 201
        object_item = create_ready_object(client)
        snapshot = create_snapshot(client, object_item["id"])
        with app.state.session_factory() as db:
            row = db.get(Snapshot, snapshot["id"])
            row.state = "queued"
            db.add(
                AnalysisAttempt(
                    snapshot_id=row.id,
                    attempt_number=1,
                    state="analyzing",
                    provider="test",
                    model="test",
                    prompt_version="test",
                )
            )
            db.commit()

    restarted = app_with_storage(engine, storage)
    with TestClient(restarted):
        with restarted.state.session_factory() as db:
            row = db.get(Snapshot, snapshot["id"])
            attempt = db.scalar(
                select(AnalysisAttempt).where(AnalysisAttempt.snapshot_id == snapshot["id"])
            )
            assert row.state == "error"
            assert attempt.error_code == "process_interrupted"
