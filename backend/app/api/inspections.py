from __future__ import annotations

import hashlib
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..day_rules import calculate_day
from ..models import (
    ConstructionObject,
    Inspection,
    InspectionAttachment,
    PlanItem,
    User,
    new_id,
)
from ..schemas import DayEvaluationResponse, InspectionResponse
from ..storage import StorageError
from .dependencies import get_current_user
from .snapshots import _validate_image
from .w2_common import owned_object


router = APIRouter(tags=["inspections", "day-evaluation"])
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "application/pdf": "pdf",
}


def _attachment_payload(item: InspectionAttachment, storage) -> dict:
    try:
        url = storage.presigned_get(item.storage_key)
    except StorageError:
        url = ""
    return {
        "id": item.id,
        "original_name": item.original_name,
        "content_type": item.content_type,
        "byte_size": item.byte_size,
        "sha256": item.sha256,
        "url": url,
    }


def _inspection_payload(
    db: Session, item: Inspection, storage, *, superseded: Optional[bool] = None
) -> dict:
    attachments = db.scalars(
        select(InspectionAttachment)
        .where(InspectionAttachment.inspection_id == item.id)
        .order_by(InspectionAttachment.id)
    ).all()
    if superseded is None:
        superseded = (
            db.scalar(
                select(Inspection.id)
                .where(
                    Inspection.object_id == item.object_id,
                    Inspection.plan_item_id == item.plan_item_id,
                    Inspection.created_at > item.created_at,
                )
                .limit(1)
            )
            is not None
        )
    return {
        "id": item.id,
        "object_id": item.object_id,
        "plan_item_id": item.plan_item_id,
        "observed_date": item.observed_date,
        "valid_until": item.valid_until,
        "verdict": item.verdict,
        "author": item.author,
        "role": item.role,
        "comment": item.comment,
        "superseded": superseded,
        "attachments": [_attachment_payload(row, storage) for row in attachments],
        "created_at": item.created_at,
    }


@router.post(
    "/objects/{object_id}/inspections",
    response_model=InspectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_inspection(
    object_id: str,
    request: Request,
    plan_item_id: str = Form(),
    observed_date: date = Form(),
    valid_until: Optional[date] = Form(default=None),
    verdict: str = Form(),
    author: str = Form(),
    role: str = Form(default=""),
    comment: str = Form(),
    files: List[UploadFile] = File(default=[]),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InspectionResponse:
    object_item = owned_object(db, user, object_id)
    plan_item = db.scalar(
        select(PlanItem).where(
            PlanItem.id == plan_item_id,
            PlanItem.object_id == object_id,
            PlanItem.is_archived.is_(False),
        )
    )
    if plan_item is None:
        raise HTTPException(status_code=422, detail="Этап не принадлежит объекту")
    if verdict not in {"confirmed", "rejected", "note"}:
        raise HTTPException(status_code=422, detail="Неизвестный вывод осмотра")
    author = author.strip()
    role = role.strip()
    comment = comment.strip()
    if not author or not comment:
        raise HTTPException(status_code=422, detail="Укажите автора и комментарий")
    if not plan_item.start_date <= observed_date <= plan_item.end_date:
        raise HTTPException(status_code=422, detail="Дата осмотра должна входить в период этапа")
    if valid_until is not None:
        if plan_item.observability not in {"no", "partial"}:
            raise HTTPException(
                status_code=422,
                detail="Период действия доступен только для невидимых или частично видимых работ",
            )
        if not observed_date <= valid_until <= plan_item.end_date:
            raise HTTPException(status_code=422, detail="Проверьте окончание периода осмотра")
    if len(files) > 3:
        raise HTTPException(status_code=422, detail="К осмотру можно приложить не более трёх файлов")

    prepared: list[tuple[UploadFile, bytes, str, str]] = []
    for file in files:
        body = await file.read(MAX_ATTACHMENT_BYTES + 1)
        if not body:
            raise HTTPException(status_code=422, detail=f"Файл {file.filename or ''} пуст")
        if len(body) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(status_code=413, detail="Файл больше 20 МБ")
        media_type = (file.content_type or "").lower()
        if media_type not in ALLOWED_ATTACHMENT_TYPES:
            raise HTTPException(status_code=415, detail="Поддерживаются JPEG, PNG и PDF")
        if media_type == "application/pdf":
            if not body.startswith(b"%PDF-"):
                raise HTTPException(status_code=422, detail="Файл не является корректным PDF")
            extension = "pdf"
        else:
            media_type, extension = _validate_image(body)
        prepared.append((file, body, extension, media_type))

    item = Inspection(
        object_id=object_id,
        plan_item_id=plan_item_id,
        observed_date=observed_date,
        valid_until=valid_until,
        verdict=verdict,
        author=author,
        role=role,
        comment=comment,
    )
    db.add(item)
    db.flush()
    stored_keys: list[str] = []
    try:
        for file, body, extension, media_type in prepared:
            attachment_id = new_id()
            relative_key = f"inspections/{object_id}/{item.id}/{attachment_id}.{extension}"
            stored = request.app.state.storage.put(
                relative_key,
                body,
                media_type,
            )
            stored_keys.append(stored.key)
            db.add(
                InspectionAttachment(
                    id=attachment_id,
                    inspection_id=item.id,
                    storage_key=stored.key,
                    original_name=file.filename or f"attachment.{extension}",
                    content_type=media_type,
                    byte_size=len(body),
                    sha256=hashlib.sha256(body).hexdigest(),
                )
            )
        db.flush()
        calculate_day(db, object_item, observed_date)
        db.commit()
    except StorageError as exc:
        db.rollback()
        for key in stored_keys:
            try:
                request.app.state.storage.delete(key)
            except StorageError:
                pass
        raise HTTPException(status_code=503, detail="Не удалось сохранить вложение") from exc
    except Exception:
        db.rollback()
        for key in stored_keys:
            try:
                request.app.state.storage.delete(key)
            except StorageError:
                pass
        raise
    return InspectionResponse.model_validate(
        _inspection_payload(db, item, request.app.state.storage, superseded=False)
    )


@router.get("/objects/{object_id}/inspections", response_model=List[InspectionResponse])
def list_inspections(
    object_id: str,
    request: Request,
    plan_item_id: Optional[str] = None,
    on_date: Optional[date] = None,
    verdict: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[InspectionResponse]:
    owned_object(db, user, object_id)
    query = select(Inspection).where(Inspection.object_id == object_id)
    if plan_item_id:
        query = query.where(Inspection.plan_item_id == plan_item_id)
    if on_date:
        query = query.where(
            Inspection.observed_date <= on_date,
            (
                (Inspection.valid_until.is_not(None))
                & (Inspection.valid_until >= on_date)
            )
            | (
                (Inspection.valid_until.is_(None))
                & (Inspection.observed_date == on_date)
            ),
        )
    if verdict:
        query = query.where(Inspection.verdict == verdict)
    rows = list(db.scalars(query.order_by(Inspection.observed_date.desc(), Inspection.created_at.desc())).all())
    latest_ids: set[str] = set()
    for row in rows:
        if not any(item.plan_item_id == row.plan_item_id for item in rows if item.id in latest_ids):
            latest_ids.add(row.id)
    return [
        InspectionResponse.model_validate(
            _inspection_payload(db, row, request.app.state.storage, superseded=row.id not in latest_ids)
        )
        for row in rows
    ]


@router.get("/objects/{object_id}/days/{evaluation_date}", response_model=DayEvaluationResponse)
def get_day_evaluation(
    object_id: str,
    evaluation_date: date,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DayEvaluationResponse:
    object_item = owned_object(db, user, object_id)
    result = calculate_day(db, object_item, evaluation_date)
    db.commit()
    return DayEvaluationResponse.model_validate(result)
