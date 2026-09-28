from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ObjectSchedule, User
from ..schemas import ScheduleInput, ScheduleResponse
from .dependencies import get_current_user
from .w2_common import current_schedule, owned_object, schedule_payload


router = APIRouter(tags=["schedules"])


@router.get("/objects/{object_id}/schedule", response_model=ScheduleResponse)
def get_schedule(
    object_id: str,
    on_date: Optional[date] = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScheduleResponse:
    owned_object(db, user, object_id)
    return ScheduleResponse.model_validate(schedule_payload(current_schedule(db, object_id, on_date)))


@router.get("/objects/{object_id}/schedule/versions", response_model=List[ScheduleResponse])
def get_schedule_versions(
    object_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[ScheduleResponse]:
    owned_object(db, user, object_id)
    rows = db.scalars(
        select(ObjectSchedule)
        .where(ObjectSchedule.object_id == object_id)
        .order_by(ObjectSchedule.version)
    ).all()
    return [ScheduleResponse.model_validate(schedule_payload(item)) for item in rows]


@router.put("/objects/{object_id}/schedule", response_model=ScheduleResponse)
def update_schedule(
    object_id: str,
    payload: ScheduleInput,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScheduleResponse:
    owned_object(db, user, object_id)
    latest = db.scalar(
        select(ObjectSchedule)
        .where(ObjectSchedule.object_id == object_id)
        .order_by(ObjectSchedule.version.desc())
    )
    if (
        latest is not None
        and latest.effective_from == payload.effective_from
        and list(latest.times) == payload.times
        and latest.confirmation_threshold == payload.confirmation_threshold
        and latest.absence_threshold == payload.absence_threshold
    ):
        return ScheduleResponse.model_validate(schedule_payload(latest))
    last_version = db.scalar(
        select(func.max(ObjectSchedule.version)).where(ObjectSchedule.object_id == object_id)
    ) or 0
    schedule = ObjectSchedule(
        object_id=object_id,
        version=last_version + 1,
        effective_from=payload.effective_from,
        times=payload.times,
        confirmation_threshold=payload.confirmation_threshold,
        absence_threshold=payload.absence_threshold,
    )
    db.add(schedule)
    db.commit()
    return ScheduleResponse.model_validate(schedule_payload(schedule))
