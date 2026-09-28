from __future__ import annotations

from datetime import datetime
import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..catalog import directory_entry
from ..database import get_db
from ..models import Camera, ConstructionObject, ObjectSchedule, PlanItem, PlanItemRevision, User
from ..schemas import ObjectCreate, ObjectDetailResponse, ObjectListItem, ObjectPatch, PlanItemInput
from .dependencies import get_current_user
from .w2_common import object_detail, owned_object, plan_snapshot, record_plan_revision


router = APIRouter(prefix="/objects", tags=["objects"])


def _stage_code(name: str) -> str:
    slug = re.sub(r"[^a-z0-9а-яё]+", "-", name.casefold()).strip("-")
    return f"custom.{slug[:90] or 'stage'}"


def _add_plan_item(
    db: Session,
    object_item: ConstructionObject,
    payload: PlanItemInput,
    camera_map: dict[str, str],
    sort_order: int,
    parent_id: str | None = None,
) -> PlanItem:
    entry = directory_entry(object_item.object_type, code=payload.stage_code, name=payload.name)
    item = PlanItem(
        object_id=object_item.id,
        parent_id=parent_id,
        stage_code=(entry or {}).get("code") or payload.stage_code or _stage_code(payload.name),
        name=payload.name,
        note=payload.note,
        start_date=payload.start_date,
        end_date=payload.end_date,
        confirmation_method=payload.confirmation_method,
        observability=payload.observability,
        camera_ids=[camera_map.get(camera_id, camera_id) for camera_id in payload.camera_ids],
        profile_snapshot=(entry or {}).get("profile", {}),
        is_outside_directory=entry is None,
        sort_order=sort_order,
    )
    db.add(item)
    db.flush()
    db.add(
        PlanItemRevision(
            object_id=object_item.id,
            plan_item_id=item.id,
            version=item.version,
            event="created",
            snapshot=plan_snapshot(item),
        )
    )
    for child_index, child in enumerate(payload.children):
        _add_plan_item(db, object_item, child, camera_map, child_index, item.id)
    return item


@router.get("", response_model=List[ObjectListItem])
def list_objects(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> List[ObjectListItem]:
    rows = db.scalars(
        select(ConstructionObject)
        .where(ConstructionObject.owner_id == user.id)
        .order_by(ConstructionObject.created_at)
    ).all()
    return [ObjectListItem.model_validate(item) for item in rows]


@router.post("", response_model=ObjectDetailResponse, status_code=status.HTTP_201_CREATED)
def create_object(
    payload: ObjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ObjectDetailResponse:
    item = ConstructionObject(
        owner_id=user.id,
        name=payload.name,
        object_type=payload.object_type,
        address=payload.address,
        timezone=payload.timezone,
        is_draft=payload.is_draft,
    )
    db.add(item)
    db.flush()

    camera_map: dict[str, str] = {}
    cameras: list[Camera] = []
    for index, camera_payload in enumerate(payload.cameras):
        camera = Camera(
            object_id=item.id,
            code=f"CAM-{index + 1:02d}",
            name=camera_payload.name,
            zone=camera_payload.zone,
            sort_order=index,
            passport={
                "view_description": camera_payload.view_description,
                "view_type": camera_payload.view_type,
                "placement": camera_payload.placement,
                "orientation": camera_payload.orientation,
                "coverage": camera_payload.coverage,
            },
        )
        db.add(camera)
        db.flush()
        cameras.append(camera)
        for key in (camera_payload.client_id, camera_payload.id):
            if key:
                camera_map[key] = camera.id

    valid_camera_ids = {camera.id for camera in cameras}
    for plan_index, plan_item in enumerate(payload.plan_items):
        requested = {
            camera_map.get(camera_id, camera_id)
            for camera_id in plan_item.camera_ids
        }
        requested.update(
            camera_map.get(camera_id, camera_id)
            for child in plan_item.children
            for camera_id in child.camera_ids
        )
        if not requested.issubset(valid_camera_ids):
            raise HTTPException(status_code=422, detail="Этап ссылается на чужую или неизвестную камеру")
        _add_plan_item(db, item, plan_item, camera_map, plan_index)

    schedule = payload.schedule
    db.add(
        ObjectSchedule(
            object_id=item.id,
            version=1,
            effective_from=schedule.effective_from,
            times=schedule.times,
            confirmation_threshold=schedule.confirmation_threshold,
            absence_threshold=schedule.absence_threshold,
        )
    )
    db.commit()
    return ObjectDetailResponse.model_validate(object_detail(db, item))


@router.get("/{object_id}", response_model=ObjectDetailResponse)
def get_object(
    object_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ObjectDetailResponse:
    return ObjectDetailResponse.model_validate(object_detail(db, owned_object(db, user, object_id)))


@router.patch("/{object_id}", response_model=ObjectDetailResponse)
def update_object(
    object_id: str,
    payload: ObjectPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ObjectDetailResponse:
    item = owned_object(db, user, object_id)
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(item, key, value)
    item.updated_at = datetime.utcnow()
    if "object_type" in changes:
        plan_rows = db.scalars(
            select(PlanItem).where(
                PlanItem.object_id == item.id,
                PlanItem.is_archived.is_(False),
            )
        ).all()
        for plan_item in plan_rows:
            entry = directory_entry(item.object_type, code=plan_item.stage_code, name=plan_item.name)
            plan_item.is_outside_directory = entry is None
            plan_item.profile_snapshot = (entry or {}).get("profile", {})
            plan_item.version += 1
            record_plan_revision(db, plan_item, "object_type_changed")
    if item.is_draft is False:
        active_camera = db.scalar(
            select(Camera.id).where(Camera.object_id == item.id, Camera.is_active.is_(True)).limit(1)
        )
        active_plan = db.scalar(
            select(PlanItem.id).where(PlanItem.object_id == item.id, PlanItem.is_archived.is_(False)).limit(1)
        )
        if not active_camera or not active_plan:
            raise HTTPException(
                status_code=422,
                detail="Для завершения настройки нужны активная камера и этап плана",
            )
    db.commit()
    return ObjectDetailResponse.model_validate(object_detail(db, item))
