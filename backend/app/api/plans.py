from __future__ import annotations

from datetime import datetime
import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..catalog import directory_entry
from ..database import get_db
from ..models import Camera, PlanItem, PlanItemRevision, User
from ..schemas import PlanGroupRequest, PlanItemInput, PlanItemPatch, PlanItemResponse
from .dependencies import get_current_user
from .w2_common import (
    owned_object,
    owned_plan_item,
    plan_snapshot,
    plan_tree,
    record_plan_revision,
)


router = APIRouter(tags=["plan"])


def _custom_code(name: str) -> str:
    slug = re.sub(r"[^a-z0-9а-яё]+", "-", name.casefold()).strip("-")
    return f"custom.{slug[:90] or 'stage'}"


def _active_plan(db: Session, object_id: str) -> list[PlanItem]:
    return list(
        db.scalars(
            select(PlanItem)
            .where(PlanItem.object_id == object_id, PlanItem.is_archived.is_(False))
            .order_by(PlanItem.sort_order, PlanItem.created_at)
        ).all()
    )


def _validate_camera_ids(db: Session, object_id: str, camera_ids: list[str]) -> None:
    valid = set(db.scalars(select(Camera.id).where(Camera.object_id == object_id)).all())
    if not set(camera_ids).issubset(valid):
        raise HTTPException(status_code=422, detail="Этап ссылается на чужую или неизвестную камеру")


def _apply_item(item: PlanItem, payload: PlanItemInput | PlanItemPatch, object_type: str) -> None:
    changes = payload.model_dump(exclude_unset=True, exclude={"children", "client_id", "id", "parent_id"})
    if "start_date" in changes or "end_date" in changes:
        start = changes.get("start_date", item.start_date)
        end = changes.get("end_date", item.end_date)
        if start > end:
            raise HTTPException(status_code=422, detail="Дата окончания не может быть раньше начала")
    for key, value in changes.items():
        setattr(item, key, value)
    entry = directory_entry(object_type, code=item.stage_code, name=item.name)
    item.stage_code = (entry or {}).get("code") or item.stage_code or _custom_code(item.name)
    item.profile_snapshot = (entry or {}).get("profile", {})
    item.is_outside_directory = entry is None
    item.updated_at = datetime.utcnow()


@router.get("/objects/{object_id}/plan", response_model=List[PlanItemResponse])
def get_plan(
    object_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[PlanItemResponse]:
    owned_object(db, user, object_id)
    return [PlanItemResponse.model_validate(item) for item in plan_tree(_active_plan(db, object_id))]


@router.put("/objects/{object_id}/plan", response_model=List[PlanItemResponse])
def synchronize_plan(
    object_id: str,
    payload: List[PlanItemInput],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[PlanItemResponse]:
    object_item = owned_object(db, user, object_id)
    if not payload and not object_item.is_draft:
        raise HTTPException(status_code=422, detail="У настроенного объекта должен остаться этап плана")

    existing = _active_plan(db, object_id)
    by_id = {item.id: item for item in existing}
    refs: dict[str, PlanItem] = {}
    seen: set[str] = set()

    flat: list[tuple[PlanItemInput, int, str | None]] = []
    for top_index, top in enumerate(payload):
        top_ref = top.id or top.client_id or f"top-{top_index}"
        flat.append((top, top_index, None))
        for child_index, child in enumerate(top.children):
            flat.append((child, child_index, top_ref))

    all_camera_ids = [camera_id for item, _, _ in flat for camera_id in item.camera_ids]
    _validate_camera_ids(db, object_id, all_camera_ids)

    for data, sort_order, _parent_ref in flat:
        supplied_ref = data.id or data.client_id
        item = by_id.get(data.id or "")
        event = "updated"
        if item is None:
            item = PlanItem(
                object_id=object_id,
                stage_code=data.stage_code or _custom_code(data.name),
                name=data.name,
                note=data.note,
                start_date=data.start_date,
                end_date=data.end_date,
                confirmation_method=data.confirmation_method,
                observability=data.observability,
                camera_ids=data.camera_ids,
                profile_snapshot={},
                sort_order=sort_order,
            )
            db.add(item)
            db.flush()
            event = "created"
        else:
            item.version += 1
        _apply_item(item, data, object_item.object_type)
        item.sort_order = sort_order
        item.is_archived = False
        refs[item.id] = item
        if supplied_ref:
            refs[supplied_ref] = item
        seen.add(item.id)
        record_plan_revision(db, item, event)

    for data, _sort_order, parent_ref in flat:
        item = refs.get(data.id or data.client_id or "")
        if item is None:
            continue
        new_parent_id = refs[parent_ref].id if parent_ref else None
        if item.parent_id != new_parent_id:
            item.parent_id = new_parent_id
            item.version += 1
            record_plan_revision(db, item, "grouped" if new_parent_id else "ungrouped")

    for item in existing:
        if item.id not in seen:
            item.is_archived = True
            item.version += 1
            item.updated_at = datetime.utcnow()
            record_plan_revision(db, item, "archived")

    db.commit()
    return [PlanItemResponse.model_validate(item) for item in plan_tree(_active_plan(db, object_id))]


@router.post(
    "/objects/{object_id}/plan/items",
    response_model=PlanItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_plan_item(
    object_id: str,
    payload: PlanItemInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlanItemResponse:
    object_item = owned_object(db, user, object_id)
    if payload.children:
        raise HTTPException(status_code=422, detail="Добавьте подэтапы отдельными операциями")
    _validate_camera_ids(db, object_id, payload.camera_ids)
    item = PlanItem(
        object_id=object_id,
        stage_code=payload.stage_code or _custom_code(payload.name),
        name=payload.name,
        note=payload.note,
        start_date=payload.start_date,
        end_date=payload.end_date,
        confirmation_method=payload.confirmation_method,
        observability=payload.observability,
        camera_ids=payload.camera_ids,
        profile_snapshot={},
        sort_order=len(_active_plan(db, object_id)),
    )
    _apply_item(item, payload, object_item.object_type)
    db.add(item)
    db.flush()
    record_plan_revision(db, item, "created")
    db.commit()
    response = plan_snapshot(item)
    response.pop("is_archived", None)
    response["children"] = []
    return PlanItemResponse.model_validate(response)


@router.patch("/plan/items/{item_id}", response_model=PlanItemResponse)
def update_plan_item(
    item_id: str,
    payload: PlanItemPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PlanItemResponse:
    item = owned_plan_item(db, user, item_id)
    object_item = owned_object(db, user, item.object_id)
    changes = payload.model_dump(exclude_unset=True)
    if "camera_ids" in changes:
        _validate_camera_ids(db, item.object_id, changes["camera_ids"])
    if "parent_id" in changes and changes["parent_id"]:
        parent = owned_plan_item(db, user, changes["parent_id"])
        if parent.object_id != item.object_id or parent.parent_id is not None or parent.id == item.id:
            raise HTTPException(status_code=422, detail="План допускает не более двух уровней")
        item.parent_id = parent.id
    item.version += 1
    _apply_item(item, payload, object_item.object_type)
    record_plan_revision(db, item, "updated")
    db.commit()
    response = plan_snapshot(item)
    response.pop("is_archived", None)
    response["children"] = []
    return PlanItemResponse.model_validate(response)


@router.delete("/plan/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_plan_item(
    item_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    item = owned_plan_item(db, user, item_id)
    if item.parent_id is None:
        children = db.scalars(
            select(PlanItem).where(PlanItem.parent_id == item.id, PlanItem.is_archived.is_(False))
        ).all()
        if children:
            raise HTTPException(status_code=409, detail="Сначала разъедините укрупнённый этап")
    item.is_archived = True
    item.version += 1
    record_plan_revision(db, item, "archived")
    db.commit()


@router.post("/objects/{object_id}/plan/group", response_model=List[PlanItemResponse])
def group_plan_items(
    object_id: str,
    payload: PlanGroupRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[PlanItemResponse]:
    owned_object(db, user, object_id)
    unique_ids = list(dict.fromkeys(payload.item_ids))
    if len(unique_ids) < 2:
        raise HTTPException(status_code=422, detail="Выберите минимум два этапа")
    members = list(
        db.scalars(
            select(PlanItem).where(
                PlanItem.object_id == object_id,
                PlanItem.id.in_(unique_ids),
                PlanItem.is_archived.is_(False),
            )
        ).all()
    )
    if len(members) != len(unique_ids) or any(item.parent_id for item in members):
        raise HTTPException(status_code=422, detail="Объединять можно только этапы верхнего уровня")
    order = min(item.sort_order for item in members)
    group = PlanItem(
        object_id=object_id,
        stage_code=_custom_code(payload.name),
        name=payload.name.strip(),
        note="",
        start_date=min(item.start_date for item in members),
        end_date=max(item.end_date for item in members),
        confirmation_method=payload.confirmation_method,
        observability=(
            "yes" if any(item.observability == "yes" for item in members)
            else "partial" if any(item.observability == "partial" for item in members)
            else "no"
        ),
        camera_ids=list(dict.fromkeys(camera for item in members for camera in item.camera_ids)),
        profile_snapshot={"combined_from": [item.stage_code for item in members]},
        is_outside_directory=True,
        sort_order=order,
    )
    db.add(group)
    db.flush()
    record_plan_revision(db, group, "created")
    for index, item in enumerate(sorted(members, key=lambda row: row.sort_order)):
        item.parent_id = group.id
        item.sort_order = index
        item.version += 1
        record_plan_revision(db, item, "grouped")
    db.commit()
    return [PlanItemResponse.model_validate(item) for item in plan_tree(_active_plan(db, object_id))]


@router.post("/plan/items/{item_id}/ungroup", response_model=List[PlanItemResponse])
def ungroup_plan_item(
    item_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[PlanItemResponse]:
    group = owned_plan_item(db, user, item_id)
    children = list(
        db.scalars(
            select(PlanItem)
            .where(PlanItem.parent_id == group.id, PlanItem.is_archived.is_(False))
            .order_by(PlanItem.sort_order)
        ).all()
    )
    if not children:
        raise HTTPException(status_code=409, detail="У этапа нет подэтапов")
    for index, child in enumerate(children):
        child.parent_id = None
        child.sort_order = group.sort_order + index
        child.version += 1
        record_plan_revision(db, child, "ungrouped")
    group.is_archived = True
    group.version += 1
    record_plan_revision(db, group, "ungrouped")
    db.commit()
    return [PlanItemResponse.model_validate(item) for item in plan_tree(_active_plan(db, group.object_id))]


@router.get("/plan/items/{item_id}/revisions")
def get_plan_item_revisions(
    item_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    owned_plan_item(db, user, item_id)
    rows = db.scalars(
        select(PlanItemRevision)
        .where(PlanItemRevision.plan_item_id == item_id)
        .order_by(PlanItemRevision.created_at, PlanItemRevision.version)
    ).all()
    return [
        {
            "id": row.id,
            "version": row.version,
            "event": row.event,
            "snapshot": row.snapshot,
            "created_at": row.created_at,
        }
        for row in rows
    ]
