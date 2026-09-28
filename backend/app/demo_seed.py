"""Демо-набор аккаунта demo/demo.

Набор описан декларативно (DEMO_OBJECTS) и живёт в двух операциях:

- seed_demo — создаёт объекты, загружает кадры из manifest и прогоняет их через настоящий анализ
  и сравнения. Модель вызывается только здесь;
- roll_demo — переносит готовый набор на новый день показа без вызова модели: сдвигает даты
  снимков и осмотров так, что последний показательный день становится «сегодня», возвращает
  объекты, камеры, расписание и план к описанию набора и убирает всё, что добавили на показе.
  Ответы модели остаются теми, что были получены при seed_demo, и открываются в режиме
  разработчика как есть.

Этапы демо-плана идут в период показа (settings.demo_period_start…end) и не сдвигаются.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .analysis import PROMPT_VERSION, build_plan_snapshot, provider_config, run_analysis_job
from .api.w2_common import record_plan_revision
from .bootstrap import ensure_demo_account
from .catalog import directory_entry
from .config import Settings
from .models import (
    AnalysisAttempt,
    Camera,
    ConstructionObject,
    DayEvaluation,
    Inspection,
    ObjectSchedule,
    PlanItem,
    Snapshot,
    SnapshotImage,
    TemporalComparison,
    User,
)
from .storage import StorageError
from .temporal import PROMPT_VERSION as COMPARISON_PROMPT_VERSION, run_comparison

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = PROJECT_ROOT / "demo/image-manifest.json"
SEED_KEY_PREFIX = "demo-seed:"

MAIN_OBJECT_NAME = "ЖК Северный парк"
SECOND_OBJECT_NAME = "Деловой центр Речной"
DRAFT_OBJECT_NAME = "Школа Южная"
SHOWCASE_SLOTS = ("09:00", "12:00", "15:00")
RIVER_SLOTS = ("09:00", "13:00", "17:00")


def _camera(code, name, zone, description, view_type, placement, orientation, coverage):
    return {
        "code": code,
        "name": name,
        "zone": zone,
        "passport": {
            "view_description": description,
            "view_type": view_type,
            "placement": placement,
            "orientation": orientation,
            "coverage": coverage,
        },
    }


# period: "show" — весь период показа; "before" — закончен до показа; "after" — начнётся после;
# [от, до] — дни относительно начала периода показа. Прошедшие и будущие этапы дают полный
# календарный план; в анализ и дневную оценку попадают только этапы, идущие в день проверки.
DEMO_OBJECTS: list[dict[str, Any]] = [
    {
        "key": "north",
        "name": MAIN_OBJECT_NAME,
        "object_type": "Жильё",
        "address": "Москва, ул. Строителей, 24",
        "is_draft": False,
        "frames": "showcase_history",
        "cameras": [
            _camera("CAM-01", "Котлован", "Северная сторона", "Котлован и северная граница площадки",
                    "fixed detail", "северная часть объекта", "south", ["котлован", "северная граница"]),
            _camera("CAM-02", "Въезд", "Ворота № 1", "Въездная группа и разгрузочная площадка",
                    "fixed detail", "западная граница объекта", "east", ["въезд", "проезд", "разгрузка"]),
            _camera("CAM-03", "Общий план", "Северо-восточная часть", "Общий вид котлована и корпуса 1",
                    "fixed overview", "северо-восточная часть объекта", "south-west",
                    ["котлован", "корпус 1", "проезд"]),
        ],
        "times": ["09:00", "12:00", "15:00", "18:00"],
        "plan": [
            {"code": "10.10", "period": [-110, -104], "cameras": []},
            {"code": "10.5", "period": [-105, -92], "cameras": ["CAM-03"]},
            {"code": "10.11", "period": [-95, -66], "cameras": ["CAM-02"]},
            {"code": "10.13", "period": [-70, -65], "cameras": []},
            {"code": "12.3.5", "period": [-65, -21], "cameras": ["CAM-01", "CAM-03"]},
            {"code": "12.3.4-crane", "period": [-24, -6], "cameras": ["CAM-03"]},
            {"code": "custom.zero-cycle", "name": "Нулевой цикл", "period": "show",
             "cameras": ["CAM-01", "CAM-03"]},
            {"code": "12.3.1", "parent": "custom.zero-cycle", "period": "show",
             "cameras": ["CAM-01", "CAM-03"]},
            {"code": "12.3.4", "parent": "custom.zero-cycle", "period": "show", "cameras": ["CAM-03"],
             "method": "inspection"},
            {"code": "12.4.4", "period": "show", "cameras": ["CAM-03"]},
            {"code": "12.5.2", "period": "show", "cameras": []},
            {"code": "12.3.10", "period": [24, 53], "cameras": []},
            {"code": "12.3.7-backfill", "period": [45, 75], "cameras": ["CAM-01", "CAM-03"]},
            {"code": "12.4.8", "period": [40, 160], "cameras": ["CAM-03"]},
            {"code": "12.4.11", "period": [110, 250], "cameras": ["CAM-03"]},
            {"code": "12.4.38", "period": [130, 220], "cameras": ["CAM-03"]},
            {"code": "12.5.1", "period": [150, 230], "cameras": ["CAM-01"]},
            {"code": "12.4.31", "period": [170, 215], "cameras": ["CAM-03"]},
            {"code": "12.6.2", "period": [200, 330], "cameras": []},
            {"code": "12.6.9", "period": [260, 320], "cameras": []},
            {"code": "12.7.4", "period": [290, 320], "cameras": ["CAM-01", "CAM-03"]},
            {"code": "12.7.1", "period": [305, 350], "cameras": ["CAM-02", "CAM-03"]},
            {"code": "12.7.2", "period": [320, 355], "cameras": ["CAM-03"]},
            {"code": "12.7.3", "period": [335, 360], "cameras": ["CAM-03"]},
        ],
        "inspections": [
            {"plan": "12.5.2", "offset": 0, "until": "period_end", "verdict": "confirmed",
             "author": "Марина Зуева", "role": "Инженер технадзора",
             "comment": "Прокладка внутренних сетей в корпусе 1 идёт по плану; "
                        "внешние камеры эти работы не видят."},
        ],
    },
    {
        "key": "river",
        "name": SECOND_OBJECT_NAME,
        "object_type": "Офисно-деловой центр",
        "address": "Москва, Речной проезд, 7",
        "is_draft": False,
        "frames": "river_history",
        "cameras": [
            _camera("CAM-01", "Котлован", "Северная сторона", "Котлован и зона земляных работ",
                    "fixed detail", "северная граница", "south", ["котлован"]),
            _camera("CAM-02", "Въезд", "Западная сторона", "Въезд и складирование материалов",
                    "fixed detail", "западная граница", "east", ["въезд", "склад материалов"]),
            _camera("CAM-03", "Общий план", "Южная сторона",
                    "Общий вид котлована: в нижней правой части полностью видна размеченная "
                    "площадка под фундамент башенного крана, слева лежат секции крана",
                    "fixed overview", "южная граница объекта", "north",
                    ["котлован", "вся площадка фундамента крана", "склад секций"]),
        ],
        "times": list(RIVER_SLOTS),
        "plan": [
            {"code": "10.10", "period": [-90, -84], "cameras": []},
            {"code": "10.11", "period": [-80, -51], "cameras": ["CAM-02"]},
            {"code": "10.13", "period": [-55, -50], "cameras": []},
            {"code": "12.3.5", "period": [-45, -3], "cameras": ["CAM-01", "CAM-03"]},
            {"code": "12.3.1", "period": "show", "cameras": ["CAM-01", "CAM-03"]},
            {"code": "12.3.4-crane", "period": "show", "cameras": ["CAM-03"]},
            {"code": "12.3.4", "period": [24, 70], "cameras": ["CAM-03"]},
            {"code": "12.3.9", "period": [60, 130], "cameras": ["CAM-01", "CAM-03"]},
            {"code": "12.3.10", "period": [110, 150], "cameras": []},
            {"code": "12.3.7-backfill", "period": [140, 165], "cameras": ["CAM-01", "CAM-03"]},
            {"code": "12.4.4", "period": [150, 330], "cameras": ["CAM-03"]},
            {"code": "12.4.8", "period": [260, 400], "cameras": ["CAM-03"]},
            {"code": "12.4.38", "period": [330, 430], "cameras": ["CAM-03"]},
            {"code": "12.4.11", "period": [360, 480], "cameras": ["CAM-03"]},
            {"code": "12.5.2", "period": [340, 500], "cameras": []},
            {"code": "12.6.2", "period": [420, 560], "cameras": []},
            {"code": "12.7.1", "period": [520, 580], "cameras": ["CAM-02", "CAM-03"]},
            {"code": "12.7.2", "period": [550, 590], "cameras": ["CAM-03"]},
        ],
        "inspections": [
            {"plan": "12.3.4-crane", "offset": -1, "until": "same", "verdict": "note",
             "author": "Игорь Соколов", "role": "Инженер ПТО",
             "comment": "Секции крана доставлены и складированы у южной границы. Фундамент под кран "
                        "не начат, причина выясняется с подрядчиком."},
        ],
    },
    {
        "key": "south",
        "name": DRAFT_OBJECT_NAME,
        "object_type": "Образование",
        "address": "Москва, ул. Южная, 3",
        "is_draft": True,
        "frames": None,
        "cameras": [],
        "times": ["09:00", "12:00", "15:00", "18:00"],
        "plan": [],
        "inspections": [],
    },
]
DEMO_BY_KEY = {item["key"]: item for item in DEMO_OBJECTS}

_roll_lock = threading.Lock()
_rolled_for: dict[str, date] = {}


def moscow_today() -> date:
    return datetime.now(ZoneInfo("Europe/Moscow")).date()


def _period(settings: Settings, kind: str | list[int]) -> tuple[date, date]:
    start, end = settings.demo_period_start, settings.demo_period_end
    if isinstance(kind, list):
        return start + timedelta(days=kind[0]), start + timedelta(days=kind[1])
    if kind == "before":
        return start - timedelta(days=28), start - timedelta(days=1)
    if kind == "after":
        return end + timedelta(days=1), end + timedelta(days=45)
    return start, end


def _stage_fields(spec: dict[str, Any], object_type: str) -> dict[str, Any]:
    entry = directory_entry(object_type, code=spec["code"]) or {}
    observability = spec.get("observability") or entry.get("observability", "yes")
    method = spec.get("method") or entry.get("confirmation_method", "cameras")
    return {
        "name": spec.get("name") or entry.get("name", spec["code"]),
        "observability": observability,
        "confirmation_method": method,
        "profile_snapshot": dict(entry.get("profile", {})),
        "is_outside_directory": not entry and not spec["code"].startswith("custom."),
    }


def _inspection_dates(settings: Settings, spec: dict[str, Any], show_day: date) -> tuple[date, date]:
    observed = show_day + timedelta(days=spec["offset"])
    until = settings.demo_period_end if spec["until"] == "period_end" else observed
    return observed, until


# ---------------------------------------------------------------- manifest


def _checked_asset(path: Path, row: dict[str, Any], *, required: bool) -> bool:
    asset = path.parent / row["file"]
    if not asset.is_file():
        if required:
            raise ValueError(f"Нет файла показательного кадра: {asset}")
        return False
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    if row.get("sha256") and digest != row["sha256"]:
        raise ValueError(f"Контрольная сумма не совпала: {asset}")
    row["resolved_path"] = str(asset)
    row["sha256"] = digest
    return True


def load_showcase_manifest(path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    rows = manifest["sets"]["showcase_history"]["observations"]
    if len(rows) != 9:
        raise ValueError("Манифест должен содержать 9 кадров: 3 времени × 3 камеры")
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["time"], row["camera_code"])
        if key in seen:
            raise ValueError(f"Повтор кадра в манифесте: {key}")
        seen.add(key)
        if not row.get("sha256"):
            raise ValueError(f"У кадра {key} нет контрольной суммы")
        row.setdefault("day_offset", 0)
        _checked_asset(path, row, required=True)
    expected = {(slot, f"CAM-0{index}") for slot in SHOWCASE_SLOTS for index in range(1, 4)}
    if seen != expected:
        raise ValueError("В манифесте отсутствует время или камера показательного дня")
    manifest["sets"]["showcase_history"]["ready"] = True

    # Второй объект — необязательный набор: пока кадры не сгенерированы, объект создаётся
    # без снимков и честно показывает «нет данных», а не подставные результаты.
    river = manifest["sets"].get("river_history")
    if river:
        river_rows = river.get("observations", [])
        keys = [(row["day_offset"], row["time"], row["camera_code"]) for row in river_rows]
        if len(keys) != len(set(keys)):
            raise ValueError("Повтор кадра в наборе river_history")
        present = [_checked_asset(path, row, required=False) for row in river_rows]
        river["ready"] = bool(river_rows) and all(present)
        river["missing"] = [row["file"] for row, ok in zip(river_rows, present) if not ok]
    return manifest


# ---------------------------------------------------------------- create


def _demo_objects(db: Session, user: User) -> list[ConstructionObject]:
    return list(
        db.scalars(select(ConstructionObject).where(ConstructionObject.owner_id == user.id)).all()
    )


def _delete_snapshot(db: Session, storage: Any, snapshot: Snapshot) -> int:
    deleted = 0
    image_ids = [image.id for image in snapshot.images]
    if image_ids:
        for comparison in db.scalars(
            select(TemporalComparison).where(
                (TemporalComparison.first_image_id.in_(image_ids))
                | (TemporalComparison.second_image_id.in_(image_ids))
            )
        ).all():
            db.delete(comparison)
    for image in snapshot.images:
        try:
            storage.delete(image.storage_key)
            deleted += 1
        except StorageError:
            pass
    db.delete(snapshot)
    return deleted


def _delete_inspection(db: Session, storage: Any, inspection: Inspection) -> int:
    deleted = 0
    for attachment in inspection.attachments:
        try:
            storage.delete(attachment.storage_key)
            deleted += 1
        except StorageError:
            pass
    db.delete(inspection)
    return deleted


def _delete_file(storage: Any, key: str) -> int:
    try:
        storage.delete(key)
        return 1
    except StorageError:
        return 0


def _delete_object(db: Session, storage: Any, object_item: ConstructionObject) -> int:
    deleted = 0
    for snapshot in object_item.snapshots:
        deleted += sum(_delete_file(storage, image.storage_key) for image in snapshot.images)
    for inspection in object_item.inspections:
        deleted += sum(_delete_file(storage, item.storage_key) for item in inspection.attachments)
    for comparison in db.scalars(
        select(TemporalComparison).where(TemporalComparison.object_id == object_item.id)
    ).all():
        db.delete(comparison)
    db.flush()
    # Кадры и осмотры ссылаются на камеры и этапы без ORM-связи, поэтому единица работы
    # не знает порядка: удаляем их отдельным flush раньше камер и плана.
    for item in [*object_item.snapshots, *object_item.inspections, *object_item.day_evaluations]:
        db.delete(item)
    db.flush()
    for plan_item in object_item.plan_items:
        if plan_item.parent_id:
            db.delete(plan_item)
    db.flush()
    # Иначе каскад удаления объекта повторит DELETE для уже удалённых строк.
    db.expire(object_item, ["snapshots", "inspections", "day_evaluations", "plan_items"])
    db.delete(object_item)
    db.flush()
    return deleted


def clear_demo_objects(db: Session, storage: Any, user: User) -> dict[str, int]:
    objects = _demo_objects(db, user)
    files = sum(_delete_object(db, storage, item) for item in objects)
    db.commit()
    return {"objects": len(objects), "files": files}


def _create_object(db: Session, user: User, spec: dict[str, Any], settings: Settings, show_day: date):
    item = ConstructionObject(
        owner_id=user.id,
        name=spec["name"],
        object_type=spec["object_type"],
        address=spec["address"],
        timezone="Europe/Moscow",
        is_draft=spec["is_draft"],
        demo_key=spec["key"],
    )
    db.add(item)
    db.flush()
    cameras: dict[str, Camera] = {}
    for index, camera_spec in enumerate(spec["cameras"]):
        camera = Camera(
            object_id=item.id,
            code=camera_spec["code"],
            name=camera_spec["name"],
            zone=camera_spec["zone"],
            sort_order=index,
            fov_revision=1,
            passport=dict(camera_spec["passport"]),
        )
        db.add(camera)
        db.flush()
        cameras[camera.code] = camera
    db.add(
        ObjectSchedule(
            object_id=item.id,
            version=1,
            effective_from=show_day - timedelta(days=30),
            times=list(spec["times"]),
            confirmation_threshold=2,
            absence_threshold=3,
        )
    )
    plan: dict[str, PlanItem] = {}
    for index, stage in enumerate(spec["plan"]):
        start, end = _period(settings, stage["period"])
        row = PlanItem(
            object_id=item.id,
            parent_id=plan[stage["parent"]].id if stage.get("parent") else None,
            stage_code=stage["code"],
            start_date=start,
            end_date=end,
            camera_ids=[cameras[code].id for code in stage["cameras"]],
            sort_order=index,
            **_stage_fields(stage, spec["object_type"]),
        )
        db.add(row)
        db.flush()
        record_plan_revision(db, row, "created")
        plan[stage["code"]] = row
    for inspection in spec["inspections"]:
        observed, until = _inspection_dates(settings, inspection, show_day)
        db.add(
            Inspection(
                object_id=item.id,
                plan_item_id=plan[inspection["plan"]].id,
                observed_date=observed,
                valid_until=until,
                verdict=inspection["verdict"],
                author=inspection["author"],
                role=inspection["role"],
                comment=inspection["comment"],
            )
        )
    db.flush()
    return item


def _queue_snapshot(
    db: Session,
    storage: Any,
    settings: Settings,
    object_item: ConstructionObject,
    cameras: dict[str, Camera],
    observed_at: datetime,
    slot: str,
    rows: list[dict[str, Any]],
) -> tuple[str, str]:
    config = provider_config(settings)
    snapshot = Snapshot(
        object_id=object_item.id,
        observed_at=observed_at,
        state="draft",
        control_slot=slot,
        source="camera",
        plan_snapshot=build_plan_snapshot(db, object_item, observed_at.date()),
    )
    db.add(snapshot)
    db.flush()
    for row in sorted(rows, key=lambda item: item["camera_code"]):
        camera = cameras[row["camera_code"]]
        asset = Path(row["resolved_path"])
        body = asset.read_bytes()
        content_type = "image/jpeg" if asset.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        image = SnapshotImage(
            snapshot_id=snapshot.id,
            camera_id=camera.id,
            storage_key="pending",
            original_name=asset.name,
            content_type=content_type,
            byte_size=len(body),
            sha256=hashlib.sha256(body).hexdigest(),
            source="camera",
            camera_name_snapshot=camera.name,
            camera_zone_snapshot=camera.zone,
            fov_revision=camera.fov_revision,
        )
        db.add(image)
        db.flush()
        stored = storage.put(
            f"demo/{object_item.id}/{snapshot.id}/{image.id}{asset.suffix.lower()}",
            body,
            content_type,
        )
        image.storage_key = stored.key
    attempt = AnalysisAttempt(
        snapshot_id=snapshot.id,
        attempt_number=1,
        state="queued",
        provider=config.provider,
        model=config.model,
        prompt_version=PROMPT_VERSION,
        idempotency_key=f"{SEED_KEY_PREFIX}{object_item.demo_key}:{observed_at.isoformat()}",
    )
    db.add(attempt)
    snapshot.state = "queued"
    db.commit()
    return snapshot.id, attempt.id


def _run_idle_comparisons(
    session_factory: sessionmaker[Session],
    storage: Any,
    settings: Settings,
    object_id: str,
    camera_id: str,
) -> list[dict[str, Any]]:
    """Сравнения соседних кадров одной камеры — тот же вызов модели, что и кнопка «Сравнить»."""
    results = []
    with session_factory() as db:
        object_item = db.get(ConstructionObject, object_id)
        camera = db.get(Camera, camera_id)
        rows = db.execute(
            select(SnapshotImage, Snapshot)
            .join(Snapshot, Snapshot.id == SnapshotImage.snapshot_id)
            .where(
                SnapshotImage.camera_id == camera_id,
                Snapshot.state.in_(["completed", "partial"]),
            )
            .order_by(Snapshot.observed_at)
        ).all()
        config = provider_config(settings)
        for (first_image, first_snapshot), (second_image, second_snapshot) in zip(rows, rows[1:]):
            # Только соседние кадры одного дня — ночные пары сигнал не использует.
            if first_snapshot.observed_at.date() != second_snapshot.observed_at.date():
                continue
            comparison = TemporalComparison(
                object_id=object_item.id,
                camera_id=camera.id,
                first_image_id=first_image.id,
                second_image_id=second_image.id,
                state="analyzing",
                provider=config.provider,
                model=config.model,
                prompt_version=COMPARISON_PROMPT_VERSION,
            )
            db.add(comparison)
            db.commit()
            run_comparison(
                db,
                storage,
                settings,
                comparison,
                object_item,
                camera,
                first_image,
                second_image,
                first_snapshot,
                second_snapshot,
            )
            results.append(
                {
                    "pair": [
                        first_snapshot.observed_at.isoformat(),
                        second_snapshot.observed_at.isoformat(),
                    ],
                    "state": comparison.state,
                    "status": (comparison.result or {}).get("status"),
                }
            )
    return results


def _check_period(settings: Settings, show_day: date) -> None:
    if not settings.demo_period_start <= show_day <= settings.demo_period_end:
        raise ValueError(
            f"Дата {show_day.isoformat()} вне периода показа "
            f"{settings.demo_period_start.isoformat()}…{settings.demo_period_end.isoformat()}: "
            "этапы демо-плана в этот день не идут. Для репетиции сдвиньте DEMO_PERIOD_START "
            "или передайте --date внутри периода."
        )


def seed_demo(
    session_factory: sessionmaker[Session],
    storage: Any,
    settings: Settings,
    *,
    observed_date: date,
    manifest_path: Path = DEFAULT_MANIFEST,
    reset: bool = False,
) -> dict[str, Any]:
    _check_period(settings, observed_date)
    manifest = load_showcase_manifest(manifest_path)
    user = ensure_demo_account(session_factory, settings)
    with session_factory() as db:
        existing = _demo_objects(db, user)
        if existing and not reset:
            return {
                "status": "already_seeded",
                "objects": len(existing),
                "date": observed_date.isoformat(),
            }
        cleared = clear_demo_objects(db, storage, user) if existing else {"objects": 0, "files": 0}
        for spec in DEMO_OBJECTS:
            _create_object(db, user, spec, settings, observed_date)
        db.commit()
    _rolled_for.pop(user.id, None)

    queued: list[tuple[str, str, str, str]] = []
    comparisons_for: list[tuple[str, str]] = []
    missing: dict[str, list[str]] = {}
    for spec in DEMO_OBJECTS:
        frame_set = manifest["sets"].get(spec["frames"] or "") or {}
        if not spec["frames"]:
            continue
        if not frame_set.get("ready"):
            missing[spec["name"]] = frame_set.get("missing") or ["набор кадров не описан"]
            continue
        with session_factory() as db:
            object_item = db.scalar(
                select(ConstructionObject).where(
                    ConstructionObject.owner_id == user.id,
                    ConstructionObject.demo_key == spec["key"],
                )
            )
            cameras = {camera.code: camera for camera in object_item.cameras}
            groups: dict[tuple[int, str], list[dict[str, Any]]] = {}
            for row in frame_set["observations"]:
                groups.setdefault((int(row.get("day_offset", 0)), row["time"]), []).append(row)
            for (offset, slot), rows in sorted(groups.items()):
                observed_at = datetime.combine(
                    observed_date + timedelta(days=offset), time.fromisoformat(slot)
                )
                snapshot_id, attempt_id = _queue_snapshot(
                    db, storage, settings, object_item, cameras, observed_at, slot, rows
                )
                queued.append((spec["name"], observed_at.isoformat(), snapshot_id, attempt_id))
            if any(int(row.get("day_offset", 0)) < 0 for row in frame_set["observations"]):
                comparisons_for.append((object_item.id, cameras["CAM-01"].id))

    results = []
    for object_name, observed_at, snapshot_id, attempt_id in queued:
        run_analysis_job(session_factory, storage, settings, snapshot_id, attempt_id)
        with session_factory() as db:
            snapshot = db.get(Snapshot, snapshot_id)
            attempts = sorted(snapshot.attempts, key=lambda item: item.attempt_number)
            results.append(
                {
                    "object": object_name,
                    "snapshot_id": snapshot_id,
                    "observed_at": observed_at,
                    "time": observed_at[11:16],
                    "state": snapshot.state,
                    "model": attempts[-1].model if attempts else None,
                    "attempts": len(attempts),
                }
            )

    comparisons: list[dict[str, Any]] = []
    for object_id, camera_id in comparisons_for:
        comparisons += _run_idle_comparisons(session_factory, storage, settings, object_id, camera_id)
    _rolled_for[user.id] = observed_date

    return {
        "status": "seeded",
        "date": observed_date.isoformat(),
        "cleared": cleared,
        "objects": len(DEMO_OBJECTS),
        "snapshots": results,
        "comparisons": comparisons,
        "river_frames": "loaded" if SECOND_OBJECT_NAME not in missing else {
            "missing": missing[SECOND_OBJECT_NAME]
        },
    }


# ---------------------------------------------------------------- roll


def _is_seed_snapshot(snapshot: Snapshot) -> bool:
    return snapshot.source == "camera" and any(
        (attempt.idempotency_key or "").startswith(SEED_KEY_PREFIX) for attempt in snapshot.attempts
    )


def _is_seed_inspection(spec: dict[str, Any], inspection: Inspection) -> bool:
    return any(
        item["author"] == inspection.author and item["comment"] == inspection.comment
        for item in spec["inspections"]
    )


def _restore_object(db: Session, settings: Settings, item: ConstructionObject, spec: dict[str, Any],
                    show_day: date) -> None:
    item.name = spec["name"]
    item.object_type = spec["object_type"]
    item.address = spec["address"]
    item.timezone = "Europe/Moscow"
    item.is_draft = spec["is_draft"]
    item.is_archived = False

    cameras = {camera.code: camera for camera in item.cameras}
    wanted = {camera["code"]: (index, camera) for index, camera in enumerate(spec["cameras"])}
    for code, camera in cameras.items():
        if code not in wanted:
            camera.is_active = False
            continue
        index, camera_spec = wanted[code]
        camera.name = camera_spec["name"]
        camera.zone = camera_spec["zone"]
        camera.sort_order = index
        camera.passport = dict(camera_spec["passport"])
        camera.fov_revision = 1
        camera.is_active = True

    for schedule in list(item.schedules):
        if schedule.version != 1:
            db.delete(schedule)
        else:
            schedule.times = list(spec["times"])
            schedule.effective_from = show_day - timedelta(days=30)
            schedule.confirmation_threshold = 2
            schedule.absence_threshold = 3

    rows: dict[str, PlanItem] = {}
    for row in sorted(item.plan_items, key=lambda value: value.created_at):
        rows.setdefault(row.stage_code, row)
    keep = {rows[stage["code"]].id for stage in spec["plan"] if stage["code"] in rows}
    for row in item.plan_items:
        if row.id not in keep:
            row.is_archived = True
            row.parent_id = None
    for index, stage in enumerate(spec["plan"]):
        row = rows.get(stage["code"])
        if row is None:
            continue
        start, end = _period(settings, stage["period"])
        fields = _stage_fields(stage, spec["object_type"])
        row.name = fields["name"]
        row.observability = fields["observability"]
        row.confirmation_method = fields["confirmation_method"]
        row.is_outside_directory = fields["is_outside_directory"]
        row.start_date, row.end_date = start, end
        row.camera_ids = [cameras[code].id for code in stage["cameras"]]
        row.parent_id = rows[stage["parent"]].id if stage.get("parent") else None
        row.sort_order = index
        row.is_archived = False


def roll_demo(
    session_factory: sessionmaker[Session],
    storage: Any,
    settings: Settings,
    *,
    show_day: date,
) -> dict[str, Any]:
    """Перенести готовый демо-набор на show_day без вызова модели."""
    from .day_rules import calculate_day

    user = ensure_demo_account(session_factory, settings)
    with session_factory() as db:
        objects = _demo_objects(db, user)
        by_key = {item.demo_key: item for item in objects if item.demo_key in DEMO_BY_KEY}
        if set(by_key) != set(DEMO_BY_KEY):
            return {"status": "needs_seed", "found": sorted(by_key)}

        removed = {"objects": 0, "snapshots": 0, "inspections": 0, "files": 0}
        for item in objects:
            if item.demo_key not in DEMO_BY_KEY:
                removed["files"] += _delete_object(db, storage, item)
                removed["objects"] += 1

        seed_snapshots: list[tuple[ConstructionObject, Snapshot]] = []
        for key, item in by_key.items():
            spec = DEMO_BY_KEY[key]
            for snapshot in list(item.snapshots):
                if _is_seed_snapshot(snapshot):
                    seed_snapshots.append((item, snapshot))
                else:
                    removed["files"] += _delete_snapshot(db, storage, snapshot)
                    removed["snapshots"] += 1
            for inspection in list(item.inspections):
                if not _is_seed_inspection(spec, inspection):
                    removed["files"] += _delete_inspection(db, storage, inspection)
                    removed["inspections"] += 1
        db.flush()

        anchor = max((snapshot.observed_at.date() for _, snapshot in seed_snapshots), default=show_day)
        delta = show_day - anchor
        if delta:
            # Два шага, чтобы сдвиг не упёрся в уникальность «объект + время» на промежуточном шаге.
            parking = timedelta(days=36500)
            for _, snapshot in seed_snapshots:
                snapshot.observed_at += parking
            db.flush()
            for _, snapshot in seed_snapshots:
                snapshot.observed_at += delta - parking
                snapshot.uploaded_at += delta
            db.flush()

        for key, item in by_key.items():
            spec = DEMO_BY_KEY[key]
            _restore_object(db, settings, item, spec, show_day)
            plan_by_code = {row.stage_code: row for row in item.plan_items}
            for inspection in item.inspections:
                if not _is_seed_inspection(spec, inspection):
                    continue
                inspection_spec = next(
                    row for row in spec["inspections"]
                    if row["author"] == inspection.author and row["comment"] == inspection.comment
                )
                observed, until = _inspection_dates(settings, inspection_spec, show_day)
                inspection.observed_date = observed
                inspection.valid_until = until
                inspection.plan_item_id = plan_by_code[inspection_spec["plan"]].id
            for evaluation in list(item.day_evaluations):
                db.delete(evaluation)
        db.commit()

        days: dict[str, set[date]] = {}
        for item, snapshot in seed_snapshots:
            days.setdefault(item.id, set()).add(snapshot.observed_at.date())
        for key, item in by_key.items():
            if item.is_draft:
                continue
            for day in sorted(days.get(item.id, set()) | {show_day}):
                try:
                    calculate_day(db, item, day)
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.exception("Итог дня не пересчитан после переноса: %s %s", item.name, day)
    _rolled_for[user.id] = show_day
    in_period = settings.demo_period_start <= show_day <= settings.demo_period_end
    return {
        "status": "rolled",
        "date": show_day.isoformat(),
        "shifted_days": delta.days,
        "snapshots": len(seed_snapshots),
        "removed": removed,
        "warning": None if in_period else "дата вне периода показа: этапы демо-плана в этот день не идут",
    }


def ensure_demo_current(session_factory: sessionmaker[Session], storage: Any, settings: Settings) -> None:
    """Вызывается при входе в demo/demo: раз в день переносит набор на сегодняшнюю дату."""
    today = moscow_today()
    with _roll_lock:
        user = ensure_demo_account(session_factory, settings)
        if _rolled_for.get(user.id) == today:
            return
        with session_factory() as db:
            latest = db.scalar(
                select(Snapshot.observed_at)
                .join(ConstructionObject, ConstructionObject.id == Snapshot.object_id)
                .join(AnalysisAttempt, AnalysisAttempt.snapshot_id == Snapshot.id)
                .where(
                    ConstructionObject.owner_id == user.id,
                    AnalysisAttempt.idempotency_key.startswith(SEED_KEY_PREFIX),
                )
                .order_by(Snapshot.observed_at.desc())
                .limit(1)
            )
        if latest is None:
            _rolled_for[user.id] = today
            return
        if latest.date() == today:
            _rolled_for[user.id] = today
            return
        try:
            result = roll_demo(session_factory, storage, settings, show_day=today)
            logger.info("Демо-набор перенесён на %s: %s", today, result)
        except Exception:
            logger.exception("Не удалось перенести демо-набор на %s", today)
