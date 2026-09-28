from __future__ import annotations

import hashlib
import json
from datetime import date, datetime

from PIL import Image
from sqlalchemy import create_engine, func, select
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, build_session_factory
from backend.app.demo_seed import (
    DRAFT_OBJECT_NAME,
    MAIN_OBJECT_NAME,
    SECOND_OBJECT_NAME,
    load_showcase_manifest,
    moscow_today,
    roll_demo,
    seed_demo,
)
from backend.app.day_rules import calculate_day
from backend.app.models import AnalysisAttempt, Inspection, ObjectSchedule, PlanItem, TemporalComparison
from backend.app.movement import calculate_movement_signals
from backend.app.models import ConstructionObject, Snapshot, User
from backend.tests.test_w1 import make_settings
from backend.tests.test_w3 import MemoryStorage, provider_response, public_context


def _river_rows(assets, *, create_files: bool):
    rows = []
    frames = [(-2, "09:00", 1), (-2, "17:00", 1), (-1, "09:00", 1), (-1, "17:00", 1)]
    frames += [(0, slot, camera) for slot in ("09:00", "13:00", "17:00") for camera in (1, 2, 3)]
    (assets / "river").mkdir(exist_ok=True)
    for index, (offset, slot, camera) in enumerate(frames):
        filename = f"river/d{offset}-cam-0{camera}-{slot.replace(':', '')}.png"
        if create_files:
            Image.new("RGB", (50 + index, 30 + camera), "#6f7f6a").save(
                assets / filename, format="PNG"
            )
        rows.append(
            {
                "day_offset": offset,
                "time": slot,
                "camera_code": f"CAM-0{camera}",
                "file": f"assets/{filename}",
                "sha256": None,
            }
        )
    return rows


def comparison_provider(config, payload):
    context = public_context(payload)
    first, second = context["images"]
    result = {
        "status": "unchanged",
        "equipment_type": "excavator",
        "region": {"x": 0.2, "y": 0.3, "width": 0.2, "height": 0.2},
        "first_image_id": first["image_id"],
        "second_image_id": second["image_id"],
        "description": "Экскаватор остаётся в той же области кадра.",
        "confidence": 0.9,
        "limitations": ["Сравниваются только два контрольных момента."],
    }
    return (
        {"id": "cmp", "choices": [{"message": {"content": json.dumps(result)}}]},
        {},
        200,
    )


def _test_manifest(tmp_path, *, river_files: bool = True):
    observations = []
    assets = tmp_path / "assets"
    assets.mkdir()
    colors = ["#7a8a77", "#8a7766", "#667f91"]
    for time_index, slot in enumerate(("09:00", "12:00", "15:00")):
        for camera_index in range(1, 4):
            filename = f"cam-0{camera_index}-{slot.replace(':', '')}.png"
            path = assets / filename
            Image.new(
                "RGB",
                (40 + time_index, 30 + camera_index),
                colors[camera_index - 1],
            ).save(path, format="PNG")
            body = path.read_bytes()
            observations.append(
                {
                    "time": slot,
                    "camera_code": f"CAM-0{camera_index}",
                    "file": f"assets/{filename}",
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
            )
    manifest = {
        "version": "test",
        "sets": {
            "showcase_history": {"observations": observations},
            "live_example": {"files": []},
            "river_history": {"observations": _river_rows(assets, create_files=river_files)},
        },
    }
    path = tmp_path / "image-manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_showcase_manifest_is_complete_and_separate_from_live_sample() -> None:
    manifest = load_showcase_manifest()
    showcase = manifest["sets"]["showcase_history"]["observations"]
    live = manifest["sets"]["live_example"]["files"]
    river = manifest["sets"]["river_history"]
    assert len(showcase) == 9
    assert len({item["sha256"] for item in showcase}) == 9
    assert {item["sha256"] for item in showcase}.isdisjoint(
        item["sha256"] for item in live
    )
    assert river["ready"] is True
    assert river["missing"] == []
    assert len(river["observations"]) == 13
    assert len({item["sha256"] for item in river["observations"]}) == 13
    assert {item["sha256"] for item in river["observations"]}.isdisjoint(
        item["sha256"] for item in showcase + live
    )


def _seed_env(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    monkeypatch.setattr(
        "backend.app.analysis.call_provider",
        lambda config, payload: provider_response(payload),
    )
    monkeypatch.setattr("backend.app.temporal.call_provider", comparison_provider)
    return session_factory


def test_demo_seed_is_idempotent_and_reset_keeps_unrelated_storage(
    tmp_path, monkeypatch
) -> None:
    session_factory = _seed_env(monkeypatch)
    storage = MemoryStorage()
    settings = make_settings(ai_api_key="test-only")
    manifest_path = _test_manifest(tmp_path)
    day = date(2026, 10, 1)

    first = seed_demo(
        session_factory, storage, settings, observed_date=day, manifest_path=manifest_path
    )
    assert first["status"] == "seeded"
    assert first["river_frames"] == "loaded"
    # 3 проверки показательного объекта + 2+2 прошлых и 3 сегодняшних у второго объекта.
    assert [item["state"] for item in first["snapshots"]] == ["completed"] * 10
    assert len(storage.objects) == 9 + 13
    assert [item["status"] for item in first["comparisons"]] == ["unchanged"] * 4

    with session_factory() as db:
        demo_user = db.scalar(select(User).where(User.is_demo.is_(True)))
        names = sorted(
            db.scalars(
                select(ConstructionObject.name).where(ConstructionObject.owner_id == demo_user.id)
            ).all()
        )
        assert names == sorted([MAIN_OBJECT_NAME, SECOND_OBJECT_NAME, DRAFT_OBJECT_NAME])
        river = db.scalar(select(ConstructionObject).where(ConstructionObject.name == SECOND_OBJECT_NAME))
        assert sorted(camera.code for camera in river.cameras) == ["CAM-01", "CAM-02", "CAM-03"]
        signals = calculate_movement_signals(db, river.id, day)
        assert len(signals) == 1
        assert signals[0]["idle_days"] == 3
        assert signals[0]["camera_name"] == "Котлован"

    repeated = seed_demo(
        session_factory, storage, settings, observed_date=day, manifest_path=manifest_path
    )
    assert repeated["status"] == "already_seeded"
    assert len(storage.objects) == 22

    # Объект, созданный жюри в демо-аккаунте, тоже уходит при сбросе.
    with session_factory() as db:
        demo_user = db.scalar(select(User).where(User.is_demo.is_(True)))
        db.add(ConstructionObject(owner_id=demo_user.id, name="Объект жюри", object_type="Жильё"))
        db.commit()

    storage.objects["other-user/keep.png"] = b"keep"
    reset = seed_demo(
        session_factory,
        storage,
        settings,
        observed_date=day,
        manifest_path=manifest_path,
        reset=True,
    )
    assert reset["status"] == "seeded"
    assert reset["cleared"] == {"objects": 4, "files": 22}
    assert storage.objects["other-user/keep.png"] == b"keep"

    with session_factory() as db:
        demo_user = db.scalar(select(User).where(User.is_demo.is_(True)))
        object_count = db.scalar(
            select(func.count(ConstructionObject.id)).where(
                ConstructionObject.owner_id == demo_user.id
            )
        )
        snapshot_count = db.scalar(select(func.count(Snapshot.id)))
    assert object_count == 3
    assert snapshot_count == 10


def test_demo_seed_without_river_frames_creates_honest_empty_object(tmp_path, monkeypatch) -> None:
    session_factory = _seed_env(monkeypatch)
    storage = MemoryStorage()
    result = seed_demo(
        session_factory,
        storage,
        make_settings(ai_api_key="test-only"),
        observed_date=date(2026, 10, 1),
        manifest_path=_test_manifest(tmp_path, river_files=False),
    )
    assert result["status"] == "seeded"
    assert len(result["snapshots"]) == 3
    assert result["comparisons"] == []
    assert len(result["river_frames"]["missing"]) == 13
    with session_factory() as db:
        river = db.scalar(select(ConstructionObject).where(ConstructionObject.name == SECOND_OBJECT_NAME))
        assert river.snapshots == []


def test_seed_refuses_date_outside_show_period(tmp_path, monkeypatch) -> None:
    session_factory = _seed_env(monkeypatch)
    import pytest

    with pytest.raises(ValueError, match="вне периода показа"):
        seed_demo(
            session_factory,
            MemoryStorage(),
            make_settings(ai_api_key="test-only"),
            observed_date=date(2026, 9, 20),
            manifest_path=_test_manifest(tmp_path),
        )


def test_roll_moves_ready_set_to_new_day_without_model_and_drops_show_edits(
    tmp_path, monkeypatch
) -> None:
    session_factory = _seed_env(monkeypatch)
    storage = MemoryStorage()
    settings = make_settings(ai_api_key="test-only")
    seed_demo(
        session_factory, storage, settings, observed_date=date(2026, 10, 1),
        manifest_path=_test_manifest(tmp_path),
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("перенос не должен вызывать модель")

    monkeypatch.setattr("backend.app.analysis.call_provider", forbidden)
    monkeypatch.setattr("backend.app.temporal.call_provider", forbidden)

    with session_factory() as db:
        attempts_before = db.scalar(select(func.count(AnalysisAttempt.id)))
        north = db.scalar(select(ConstructionObject).where(ConstructionObject.demo_key == "north"))
        # правки жюри за день показа
        north.name = "Переименовано жюри"
        north.cameras[0].is_active = False
        north.cameras[1].fov_revision = 3
        db.add(ObjectSchedule(object_id=north.id, version=2, effective_from=date(2026, 10, 1),
                              times=["10:00"], confirmation_threshold=1, absence_threshold=1))
        db.add(PlanItem(object_id=north.id, stage_code="12.7.6", name="Ограждение территории",
                        start_date=date(2026, 10, 1), end_date=date(2026, 10, 5)))
        plan_item = next(row for row in north.plan_items if row.stage_code == "12.4.4")
        db.add(Inspection(object_id=north.id, plan_item_id=plan_item.id, observed_date=date(2026, 10, 1),
                          verdict="rejected", author="Жюри", role="", comment="Проверка"))
        manual = Snapshot(object_id=north.id, observed_at=datetime(2026, 10, 1, 18, 0), state="completed",
                          control_slot="18:00", source="manual", plan_snapshot={})
        db.add(manual)
        db.add(ConstructionObject(owner_id=north.owner_id, name="Объект жюри", object_type="Жильё"))
        db.commit()

    result = roll_demo(session_factory, storage, settings, show_day=date(2026, 10, 3))
    assert result["status"] == "rolled"
    assert result["shifted_days"] == 2
    assert result["removed"]["objects"] == 1
    assert result["removed"]["snapshots"] == 1
    assert result["removed"]["inspections"] == 1

    with session_factory() as db:
        assert db.scalar(select(func.count(AnalysisAttempt.id))) == attempts_before
        north = db.scalar(select(ConstructionObject).where(ConstructionObject.demo_key == "north"))
        river = db.scalar(select(ConstructionObject).where(ConstructionObject.demo_key == "river"))
        assert north.name == MAIN_OBJECT_NAME
        assert all(camera.is_active and camera.fov_revision == 1 for camera in north.cameras)
        assert [row.version for row in north.schedules] == [1]
        extra = next(row for row in north.plan_items if row.stage_code == "12.7.6")
        assert extra.is_archived
        assert sorted({row.observed_at.date() for row in north.snapshots}) == [date(2026, 10, 3)]
        assert sorted({row.observed_at.strftime("%H:%M") for row in north.snapshots}) == [
            "09:00", "12:00", "15:00"
        ]
        assert sorted({row.observed_at.date() for row in river.snapshots}) == [
            date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)
        ]
        inspection = next(row for row in north.inspections)
        assert inspection.observed_date == date(2026, 10, 3)
        report = calculate_day(db, north, date(2026, 10, 3))
        signals = calculate_movement_signals(db, river.id, date(2026, 10, 3))
        assert signals and signals[0]["end_date"] == "2026-10-03"
        assert db.scalar(select(func.count(TemporalComparison.id))) == 4

    # повторный перенос на тот же день ничего не сдвигает
    again = roll_demo(session_factory, storage, settings, show_day=date(2026, 10, 3))
    assert again["shifted_days"] == 0


def test_demo_login_rolls_set_to_today(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from backend.app.main import create_app
    from backend.app import demo_seed
    from backend.tests.test_w1 import ToggleMailSender

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    monkeypatch.setattr("backend.app.analysis.call_provider", lambda config, payload: provider_response(payload))
    monkeypatch.setattr("backend.app.temporal.call_provider", comparison_provider)
    storage = MemoryStorage()
    settings = make_settings(ai_api_key="test-only")
    seed_demo(build_session_factory(engine), storage, settings, observed_date=date(2026, 10, 1),
              manifest_path=_test_manifest(tmp_path))
    demo_seed._rolled_for.clear()
    app = create_app(settings, engine=engine, storage=storage, mail_sender=ToggleMailSender())
    with TestClient(app) as client:
        assert client.post("/auth/login", json={"identifier": "demo", "password": "demo"}).status_code == 200
        north = next(item for item in client.get("/objects").json() if item["name"] == MAIN_OBJECT_NAME)
        snapshots = client.get(f"/objects/{north['id']}/snapshots").json()
        assert {item["observed_at"][:10] for item in snapshots} == {moscow_today().isoformat()}
