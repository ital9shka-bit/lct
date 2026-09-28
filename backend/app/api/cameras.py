from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Camera, User
from ..schemas import CameraInput, CameraPatch, CameraResponse
from .dependencies import get_current_user
from .w2_common import (
    camera_payload,
    ensure_unique_active_camera_names,
    next_camera_code,
    owned_camera,
    owned_object,
)


router = APIRouter(tags=["cameras"])


def _apply_camera(camera: Camera, payload: CameraInput | CameraPatch) -> None:
    changes = payload.model_dump(exclude_unset=True)
    passport = dict(camera.passport or {})
    for key in ("view_description", "view_type", "placement", "orientation", "coverage"):
        if key in changes:
            passport[key] = changes.pop(key)
    for key in ("name", "zone", "sort_order", "is_active"):
        if key in changes:
            setattr(camera, key, changes[key])
    camera.passport = passport
    camera.updated_at = datetime.utcnow()


@router.get("/objects/{object_id}/cameras", response_model=List[CameraResponse])
def list_cameras(
    object_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[CameraResponse]:
    owned_object(db, user, object_id)
    rows = db.scalars(
        select(Camera).where(Camera.object_id == object_id).order_by(Camera.sort_order, Camera.created_at)
    ).all()
    return [CameraResponse.model_validate(camera_payload(item)) for item in rows]


@router.post(
    "/objects/{object_id}/cameras",
    response_model=CameraResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_camera(
    object_id: str,
    payload: CameraInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CameraResponse:
    owned_object(db, user, object_id)
    rows = list(db.scalars(select(Camera).where(Camera.object_id == object_id)).all())
    if sum(item.is_active for item in rows) >= 16:
        raise HTTPException(status_code=422, detail="У объекта может быть не более 16 активных камер")
    ensure_unique_active_camera_names(db, object_id, [payload.name])
    camera = Camera(
        object_id=object_id,
        code=next_camera_code(rows),
        name=payload.name,
        zone=payload.zone,
        sort_order=payload.sort_order,
        passport={},
    )
    _apply_camera(camera, payload)
    db.add(camera)
    db.commit()
    return CameraResponse.model_validate(camera_payload(camera))


@router.put("/objects/{object_id}/cameras", response_model=List[CameraResponse])
def synchronize_cameras(
    object_id: str,
    payload: List[CameraInput],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[CameraResponse]:
    owned_object(db, user, object_id)
    if len(payload) > 16:
        raise HTTPException(status_code=422, detail="У объекта может быть не более 16 активных камер")
    names = [item.name for item in payload]
    normalized = [name.casefold() for name in names]
    if len(normalized) != len(set(normalized)):
        raise HTTPException(status_code=422, detail="Названия активных камер должны быть уникальны")

    existing = list(db.scalars(select(Camera).where(Camera.object_id == object_id)).all())
    by_id = {item.id: item for item in existing}
    incoming_ids = {item.id for item in payload if item.id in by_id}
    for camera in existing:
        if camera.is_active and camera.id not in incoming_ids:
            camera.is_active = False
            camera.updated_at = datetime.utcnow()

    for index, item in enumerate(payload):
        camera = by_id.get(item.id or "")
        if camera is None:
            camera = Camera(
                object_id=object_id,
                code=next_camera_code(existing),
                name=item.name,
                zone=item.zone,
                sort_order=index,
                passport={},
            )
            db.add(camera)
            db.flush()
            existing.append(camera)
            by_id[camera.id] = camera
        item.sort_order = index
        _apply_camera(camera, item)
        camera.is_active = True

    db.commit()
    rows = db.scalars(
        select(Camera).where(Camera.object_id == object_id).order_by(Camera.sort_order, Camera.created_at)
    ).all()
    return [CameraResponse.model_validate(camera_payload(item)) for item in rows]


@router.patch("/cameras/{camera_id}", response_model=CameraResponse)
def update_camera(
    camera_id: str,
    payload: CameraPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CameraResponse:
    camera = owned_camera(db, user, camera_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("is_active") is True:
        count = len(
            db.scalars(
                select(Camera.id).where(
                    Camera.object_id == camera.object_id,
                    Camera.is_active.is_(True),
                )
            ).all()
        )
        if not camera.is_active and count >= 16:
            raise HTTPException(status_code=422, detail="У объекта может быть не более 16 активных камер")
    if "name" in changes and (camera.is_active or changes.get("is_active") is True):
        ensure_unique_active_camera_names(db, camera.object_id, [changes["name"]], excluding_ids={camera.id})
    _apply_camera(camera, payload)
    db.commit()
    return CameraResponse.model_validate(camera_payload(camera))


@router.post("/cameras/{camera_id}/fov-revision", response_model=CameraResponse)
def increment_fov_revision(
    camera_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CameraResponse:
    camera = owned_camera(db, user, camera_id)
    camera.fov_revision += 1
    camera.updated_at = datetime.utcnow()
    db.commit()
    return CameraResponse.model_validate(camera_payload(camera))
