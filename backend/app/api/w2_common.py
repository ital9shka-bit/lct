from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Camera,
    ConstructionObject,
    ObjectSchedule,
    PlanItem,
    PlanItemRevision,
    Snapshot,
    SnapshotImage,
    User,
)


def owned_object(db: Session, user: User, object_id: str) -> ConstructionObject:
    item = db.scalar(
        select(ConstructionObject).where(
            ConstructionObject.id == object_id,
            ConstructionObject.owner_id == user.id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Объект не найден")
    return item


def owned_camera(db: Session, user: User, camera_id: str) -> Camera:
    camera = db.scalar(
        select(Camera)
        .join(ConstructionObject, Camera.object_id == ConstructionObject.id)
        .where(Camera.id == camera_id, ConstructionObject.owner_id == user.id)
    )
    if camera is None:
        raise HTTPException(status_code=404, detail="Камера не найдена")
    return camera


def owned_plan_item(db: Session, user: User, item_id: str) -> PlanItem:
    item = db.scalar(
        select(PlanItem)
        .join(ConstructionObject, PlanItem.object_id == ConstructionObject.id)
        .where(PlanItem.id == item_id, ConstructionObject.owner_id == user.id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Этап плана не найден")
    return item


def owned_snapshot(db: Session, user: User, snapshot_id: str) -> Snapshot:
    item = db.scalar(
        select(Snapshot)
        .join(ConstructionObject, Snapshot.object_id == ConstructionObject.id)
        .where(Snapshot.id == snapshot_id, ConstructionObject.owner_id == user.id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Проверка не найдена")
    return item


def owned_snapshot_image(db: Session, user: User, image_id: str) -> SnapshotImage:
    item = db.scalar(
        select(SnapshotImage)
        .join(Snapshot, SnapshotImage.snapshot_id == Snapshot.id)
        .join(ConstructionObject, Snapshot.object_id == ConstructionObject.id)
        .where(SnapshotImage.id == image_id, ConstructionObject.owner_id == user.id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Изображение не найдено")
    return item


def camera_payload(camera: Camera) -> dict[str, Any]:
    passport = camera.passport or {}
    return {
        "id": camera.id,
        "code": camera.code,
        "name": camera.name,
        "zone": camera.zone,
        "sort_order": camera.sort_order,
        "is_active": camera.is_active,
        "view_description": passport.get("view_description", ""),
        "view_type": passport.get("view_type", "fixed overview"),
        "placement": passport.get("placement", ""),
        "orientation": passport.get("orientation", ""),
        "coverage": passport.get("coverage", []),
        "fov_revision": camera.fov_revision,
    }


def plan_snapshot(item: PlanItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "parent_id": item.parent_id,
        "stage_code": item.stage_code,
        "name": item.name,
        "note": item.note,
        "start_date": item.start_date.isoformat(),
        "end_date": item.end_date.isoformat(),
        "confirmation_method": item.confirmation_method,
        "observability": item.observability,
        "camera_ids": list(item.camera_ids or []),
        "profile_snapshot": dict(item.profile_snapshot or {}),
        "is_outside_directory": item.is_outside_directory,
        "sort_order": item.sort_order,
        "version": item.version,
        "is_archived": item.is_archived,
    }


def record_plan_revision(db: Session, item: PlanItem, event: str) -> None:
    db.add(
        PlanItemRevision(
            object_id=item.object_id,
            plan_item_id=item.id,
            version=item.version,
            event=event,
            snapshot=plan_snapshot(item),
        )
    )


def plan_tree(rows: list[PlanItem]) -> list[dict[str, Any]]:
    active = [item for item in rows if not item.is_archived]
    by_parent: dict[str, list[PlanItem]] = {}
    for item in active:
        if item.parent_id:
            by_parent.setdefault(item.parent_id, []).append(item)

    def encode(item: PlanItem) -> dict[str, Any]:
        result = plan_snapshot(item)
        result.pop("is_archived", None)
        result["children"] = [
            encode(child)
            for child in sorted(by_parent.get(item.id, []), key=lambda row: (row.sort_order, row.created_at))
        ]
        return result

    return [
        encode(item)
        for item in sorted(
            [row for row in active if row.parent_id is None],
            key=lambda row: (row.sort_order, row.created_at),
        )
    ]


def current_schedule(db: Session, object_id: str, on_date: date | None = None) -> ObjectSchedule:
    on_date = on_date or date.today()
    schedule = db.scalar(
        select(ObjectSchedule)
        .where(ObjectSchedule.object_id == object_id, ObjectSchedule.effective_from <= on_date)
        .order_by(ObjectSchedule.effective_from.desc(), ObjectSchedule.version.desc())
    )
    if schedule is None:
        schedule = db.scalar(
            select(ObjectSchedule)
            .where(ObjectSchedule.object_id == object_id)
            .order_by(ObjectSchedule.effective_from.asc(), ObjectSchedule.version.asc())
        )
    if schedule is None:
        raise HTTPException(status_code=409, detail="Расписание объекта не настроено")
    return schedule


def schedule_payload(item: ObjectSchedule) -> dict[str, Any]:
    return {
        "id": item.id,
        "version": item.version,
        "effective_from": item.effective_from,
        "times": list(item.times),
        "confirmation_threshold": item.confirmation_threshold,
        "absence_threshold": item.absence_threshold,
        "created_at": item.created_at,
    }


def object_detail(db: Session, item: ConstructionObject) -> dict[str, Any]:
    cameras = db.scalars(
        select(Camera).where(Camera.object_id == item.id).order_by(Camera.sort_order, Camera.created_at)
    ).all()
    plan = db.scalars(
        select(PlanItem).where(PlanItem.object_id == item.id).order_by(PlanItem.sort_order, PlanItem.created_at)
    ).all()
    return {
        "id": item.id,
        "name": item.name,
        "object_type": item.object_type,
        "address": item.address,
        "timezone": item.timezone,
        "is_draft": item.is_draft,
        "is_archived": item.is_archived,
        "cameras": [camera_payload(camera) for camera in cameras],
        "plan_items": plan_tree(list(plan)),
        "schedule": schedule_payload(current_schedule(db, item.id)),
    }


def ensure_unique_active_camera_names(
    db: Session,
    object_id: str,
    names: list[str],
    *,
    excluding_ids: set[str] | None = None,
) -> None:
    normalized = [name.strip().casefold() for name in names]
    if any(not name for name in normalized) or len(normalized) != len(set(normalized)):
        raise HTTPException(status_code=422, detail="Названия активных камер должны быть уникальны")
    excluding_ids = excluding_ids or set()
    existing = db.scalars(
        select(Camera).where(Camera.object_id == object_id, Camera.is_active.is_(True))
    ).all()
    occupied = {camera.name.strip().casefold() for camera in existing if camera.id not in excluding_ids}
    if occupied.intersection(normalized):
        raise HTTPException(status_code=409, detail="Название камеры уже используется")


def next_camera_code(rows: list[Camera]) -> str:
    numbers = []
    for row in rows:
        if row.code.startswith("CAM-") and row.code[4:].isdigit():
            numbers.append(int(row.code[4:]))
    return f"CAM-{max(numbers, default=0) + 1:02d}"
