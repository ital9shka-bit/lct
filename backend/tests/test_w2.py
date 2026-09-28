from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.models import Camera, PlanItem, PlanItemRevision
from backend.tests.test_w1 import make_app, register


@pytest.fixture
def engine():
    value = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(value)
    return value


def camera(name: str, client_id: str) -> dict:
    return {
        "client_id": client_id,
        "name": name,
        "zone": "Север",
        "view_type": "fixed detail",
        "orientation": "south",
        "coverage": ["котлован"],
    }


def stage(name: str, client_id: str, camera_ids: list[str] | None = None) -> dict:
    return {
        "client_id": client_id,
        "name": name,
        "start_date": "2026-09-01",
        "end_date": "2026-09-30",
        "confirmation_method": "cameras",
        "observability": "yes",
        "camera_ids": camera_ids or [],
    }


def create_payload(*, draft: bool = False) -> dict:
    return {
        "name": "Тестовый объект",
        "object_type": "Жильё",
        "address": "Москва",
        "timezone": "Europe/Moscow",
        "is_draft": draft,
        "cameras": [] if draft else [camera("Котлован", "cam-a"), camera("Въезд", "cam-b")],
        "plan_items": [] if draft else [stage("Разработка котлована", "stage-a", ["cam-a"])],
        "schedule": {
            "effective_from": "2026-09-01",
            "times": ["09:00", "12:00", "15:00", "18:00"],
            "confirmation_threshold": 2,
            "absence_threshold": 3,
        },
    }


def authenticated_client(engine, email: str = "w2@example.org") -> TestClient:
    client = TestClient(make_app(engine))
    client.__enter__()
    assert register(client, email).status_code == 201
    return client


def test_draft_can_be_empty_but_ready_object_cannot(engine) -> None:
    with authenticated_client(engine) as client:
        draft = client.post("/objects", json=create_payload(draft=True))
        assert draft.status_code == 201
        assert draft.json()["is_draft"] is True
        invalid = create_payload(draft=True)
        invalid["is_draft"] = False
        response = client.post("/objects", json=invalid)
        assert response.status_code == 422


def test_complete_object_cameras_and_plan_are_saved_atomically(engine) -> None:
    with authenticated_client(engine) as client:
        response = client.post("/objects", json=create_payload())
        assert response.status_code == 201, response.text
        body = response.json()
        assert [item["code"] for item in body["cameras"]] == ["CAM-01", "CAM-02"]
        assert body["plan_items"][0]["camera_ids"] == [body["cameras"][0]["id"]]
        assert body["plan_items"][0]["profile_snapshot"]["strong_signs"]
        assert body["schedule"]["version"] == 1

        duplicate = create_payload()
        duplicate["name"] = "Другой объект"
        duplicate["cameras"][1]["name"] = "котлован"
        assert client.post("/objects", json=duplicate).status_code == 422


def test_camera_sync_archives_removed_camera_and_keeps_code(engine) -> None:
    with authenticated_client(engine) as client:
        created = client.post("/objects", json=create_payload()).json()
        object_id = created["id"]
        first, second = created["cameras"]
        payload = [
            {
                "id": first["id"],
                "name": "Котлован север",
                "zone": "Северная сторона",
                "view_type": first["view_type"],
                "orientation": first["orientation"],
                "coverage": first["coverage"],
            }
        ]
        response = client.put(f"/objects/{object_id}/cameras", json=payload)
        assert response.status_code == 200, response.text
        rows = response.json()
        changed = next(item for item in rows if item["id"] == first["id"])
        archived = next(item for item in rows if item["id"] == second["id"])
        assert changed["code"] == "CAM-01"
        assert changed["name"] == "Котлован север"
        assert archived["is_active"] is False

        conflict = client.patch(
            f"/cameras/{second['id']}",
            json={"name": "КОТЛОВАН СЕВЕР", "is_active": True},
        )
        assert conflict.status_code == 409


def test_camera_passport_and_fov_revision_are_persisted(engine) -> None:
    with authenticated_client(engine) as client:
        created = client.post("/objects", json=create_payload()).json()
        cam = created["cameras"][0]
        updated = client.patch(
            f"/cameras/{cam['id']}",
            json={
                "view_description": "Котлован целиком",
                "placement": "Северная мачта",
                "coverage": ["котлован", "корпус 1"],
            },
        )
        assert updated.status_code == 200
        assert updated.json()["view_description"] == "Котлован целиком"
        bumped = client.post(f"/cameras/{cam['id']}/fov-revision")
        assert bumped.json()["fov_revision"] == 2
        assert bumped.json()["code"] == cam["code"]


def test_schedule_versions_are_selected_by_effective_date(engine) -> None:
    with authenticated_client(engine) as client:
        created = client.post("/objects", json=create_payload()).json()
        object_id = created["id"]
        changed = client.put(
            f"/objects/{object_id}/schedule",
            json={
                "effective_from": "2026-10-01",
                "times": ["17:00", "09:00", "13:00"],
                "confirmation_threshold": 2,
                "absence_threshold": 3,
            },
        )
        assert changed.status_code == 200
        assert changed.json()["times"] == ["09:00", "13:00", "17:00"]
        assert changed.json()["version"] == 2
        old = client.get(f"/objects/{object_id}/schedule?on_date=2026-09-15").json()
        new = client.get(f"/objects/{object_id}/schedule?on_date=2026-10-01").json()
        assert old["version"] == 1
        assert new["version"] == 2
        assert len(client.get(f"/objects/{object_id}/schedule/versions").json()) == 2
        unchanged = client.put(
            f"/objects/{object_id}/schedule",
            json={
                "effective_from": "2026-10-01",
                "times": ["09:00", "13:00", "17:00"],
                "confirmation_threshold": 2,
                "absence_threshold": 3,
            },
        )
        assert unchanged.json()["version"] == 2
        assert len(client.get(f"/objects/{object_id}/schedule/versions").json()) == 2
        duplicate = client.put(
            f"/objects/{object_id}/schedule",
            json={"times": ["09:00", "09:00"]},
        )
        assert duplicate.status_code == 422


def test_plan_group_ungroup_and_revision_history(engine) -> None:
    with authenticated_client(engine) as client:
        payload = create_payload()
        payload["plan_items"].append(stage("Монтаж башенного крана", "stage-b", ["cam-b"]))
        created = client.post("/objects", json=payload).json()
        object_id = created["id"]
        item_ids = [item["id"] for item in created["plan_items"]]
        grouped = client.post(
            f"/objects/{object_id}/plan/group",
            json={
                "item_ids": item_ids,
                "name": "Нулевой цикл",
                "confirmation_method": "cameras",
            },
        )
        assert grouped.status_code == 200, grouped.text
        group = grouped.json()[0]
        assert len(group["children"]) == 2
        assert group["start_date"] == "2026-09-01"

        ungrouped = client.post(f"/plan/items/{group['id']}/ungroup")
        assert ungrouped.status_code == 200
        assert len(ungrouped.json()) == 2
        assert all(not item["children"] for item in ungrouped.json())
        history = client.get(f"/plan/items/{item_ids[0]}/revisions").json()
        assert {row["event"] for row in history} >= {"created", "grouped", "ungrouped"}


def test_invalid_interval_and_foreign_camera_are_rejected(engine) -> None:
    with authenticated_client(engine) as client:
        created = client.post("/objects", json=create_payload()).json()
        object_id = created["id"]
        invalid = stage("Новый этап", "stage-x")
        invalid["start_date"] = "2026-10-02"
        invalid["end_date"] = "2026-10-01"
        assert client.post(f"/objects/{object_id}/plan/items", json=invalid).status_code == 422
        foreign = stage("Новый этап", "stage-y", ["not-a-camera"])
        assert client.post(f"/objects/{object_id}/plan/items", json=foreign).status_code == 422


def test_directory_filter_and_object_type_change_mark_outside_entry(engine) -> None:
    with authenticated_client(engine) as client:
        names = {
            item["name"]
            for item in client.get(
                "/stage-directory", params={"object_type": "Жильё"}
            ).json()
        }
        assert "Устройство котлована и земляные работы" in names
        assert "Покрытие дорожной одежды" not in names
        created = client.post("/objects", json=create_payload()).json()
        assert created["plan_items"][0]["stage_code"] == "12.3.1"
        changed = client.patch(
            f"/objects/{created['id']}", json={"object_type": "Спорт"}
        )
        assert changed.json()["plan_items"][0]["is_outside_directory"] is False
        changed = client.patch(
            f"/objects/{created['id']}", json={"object_type": "Дороги"}
        )
        assert changed.json()["plan_items"][0]["is_outside_directory"] is False
        created_road = client.post("/objects", json={**create_payload(), "name": "Кровля",
            "plan_items": [stage("Устройство кровли", "stage-r", ["cam-a"])]}).json()
        changed = client.patch(
            f"/objects/{created_road['id']}", json={"object_type": "Дороги"}
        )
        assert changed.status_code == 200
        assert changed.json()["plan_items"][0]["is_outside_directory"] is True


def test_w2_endpoints_do_not_leak_objects_between_users(engine) -> None:
    app = make_app(engine)
    with TestClient(app) as alice, TestClient(app) as bob:
        assert register(alice, "alice-w2@example.org").status_code == 201
        created = alice.post("/objects", json=create_payload()).json()
        assert register(bob, "bob-w2@example.org").status_code == 201
        assert bob.get(f"/objects/{created['id']}").status_code == 404
        assert bob.get(f"/objects/{created['id']}/cameras").status_code == 404
        assert bob.get(f"/objects/{created['id']}/plan").status_code == 404
        assert bob.get(f"/objects/{created['id']}/schedule").status_code == 404


def test_plan_rows_and_revisions_remain_in_database_after_ungroup(engine) -> None:
    with authenticated_client(engine) as client:
        payload = create_payload()
        payload["plan_items"].append(stage("Монтаж башенного крана", "stage-b"))
        created = client.post("/objects", json=payload).json()
        item_ids = [item["id"] for item in created["plan_items"]]
        group = client.post(
            f"/objects/{created['id']}/plan/group",
            json={"item_ids": item_ids, "name": "Группа", "confirmation_method": "cameras"},
        ).json()[0]
        client.post(f"/plan/items/{group['id']}/ungroup")
        with client.app.state.session_factory() as db:
            assert db.scalar(select(PlanItem).where(PlanItem.id == group["id"])).is_archived
            assert len(db.scalars(select(PlanItemRevision)).all()) >= 7
            assert len(db.scalars(select(Camera)).all()) == 2
