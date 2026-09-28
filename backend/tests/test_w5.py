from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.tests.test_w1 import register
from backend.tests.test_w3 import (
    MemoryStorage,
    app_with_storage,
    create_ready_object,
    image_bytes,
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


def test_history_filters_date_camera_source_and_state(engine) -> None:
    storage = MemoryStorage()
    with TestClient(app_with_storage(engine, storage)) as client:
        register(client, "w5-history@example.org")
        object_item = create_ready_object(client)
        first = client.post(
            f"/objects/{object_item['id']}/snapshots",
            json={
                "observed_date": "2026-09-18",
                "observed_time": "09:00",
                "source": "manual",
            },
        ).json()
        assert (
            upload_image(
                client,
                first["id"],
                object_item["cameras"][0]["id"],
                body=image_bytes(),
            ).status_code
            == 201
        )
        second = client.post(
            f"/objects/{object_item['id']}/snapshots",
            json={
                "observed_date": "2026-09-19",
                "observed_time": "12:00",
                "source": "camera",
            },
        ).json()
        uploaded = client.post(
            f"/snapshots/{second['id']}/images",
            data={
                "camera_id": object_item["cameras"][1]["id"],
                "source": "camera",
            },
            files={"file": ("camera.png", image_bytes("PNG"), "image/png")},
        )
        assert uploaded.status_code == 201, uploaded.text

        by_camera = client.get(
            f"/objects/{object_item['id']}/history",
            params={"camera_id": object_item["cameras"][0]["id"]},
        )
        assert [item["id"] for item in by_camera.json()] == [first["id"]]

        by_source = client.get(
            f"/objects/{object_item['id']}/history", params={"source": "camera"}
        )
        assert [item["id"] for item in by_source.json()] == [second["id"]]

        by_date = client.get(
            f"/objects/{object_item['id']}/history",
            params={"date_from": "2026-09-19", "date_to": "2026-09-19"},
        )
        assert [item["id"] for item in by_date.json()] == [second["id"]]

        drafts = client.get(
            f"/objects/{object_item['id']}/history", params={"state": "draft"}
        )
        assert len(drafts.json()) == 2
        assert (
            client.get(
                f"/objects/{object_item['id']}/history",
                params={"state": "unknown"},
            ).status_code
            == 422
        )

