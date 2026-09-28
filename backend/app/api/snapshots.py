from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta
from io import BytesIO
from typing import List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..analysis import PROMPT_VERSION, build_plan_snapshot, provider_config, run_analysis_job
from ..day_rules import nearest_control_slot
from ..database import get_db
from ..models import AnalysisAttempt, Camera, Snapshot, SnapshotImage, User, new_id
from ..schemas import (
    AnalysisAttemptResponse,
    AnalyzeResponse,
    SnapshotCreate,
    SnapshotImageResponse,
    SnapshotResponse,
)
from ..storage import StorageError
from .dependencies import get_current_user
from .w2_common import (
    current_schedule,
    owned_camera,
    owned_object,
    owned_snapshot,
    owned_snapshot_image,
)


router = APIRouter(tags=["snapshots"])
MAX_IMAGE_BYTES = 20 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png")}


def _validate_image(body: bytes) -> tuple[str, str]:
    if not body:
        raise HTTPException(status_code=422, detail="Файл пуст")
    if len(body) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Файл больше 20 МБ")
    try:
        with Image.open(BytesIO(body)) as source:
            image_format = source.format
            ImageOps.exif_transpose(source).load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=422, detail="Файл не является корректным JPEG или PNG") from exc
    if image_format not in ALLOWED_IMAGE_FORMATS:
        raise HTTPException(status_code=415, detail="Поддерживаются только JPEG и PNG")
    return ALLOWED_IMAGE_FORMATS[image_format]


def _attempt_payload(attempt: AnalysisAttempt) -> dict:
    return {
        "id": attempt.id,
        "attempt_number": attempt.attempt_number,
        "state": attempt.state,
        "provider": attempt.provider,
        "model": attempt.model,
        "prompt_version": attempt.prompt_version,
        "request_id": attempt.request_id,
        "duration_ms": attempt.duration_ms,
        "input_tokens": attempt.input_tokens,
        "output_tokens": attempt.output_tokens,
        "estimated_cost": attempt.estimated_cost,
        "raw_response": attempt.raw_response,
        "normalized_response": attempt.normalized_response,
        "error_code": attempt.error_code,
        "error_detail": attempt.error_detail,
        "created_at": attempt.created_at,
        "finished_at": attempt.finished_at,
    }


def _image_payload(image: SnapshotImage, storage) -> dict:
    try:
        url = storage.presigned_get(image.storage_key)
    except StorageError:
        url = ""
    return {
        "id": image.id,
        "camera_id": image.camera_id,
        "camera_name": image.camera_name_snapshot,
        "camera_zone": image.camera_zone_snapshot,
        "original_name": image.original_name,
        "content_type": image.content_type,
        "byte_size": image.byte_size,
        "sha256": image.sha256,
        "source": image.source,
        "fov_revision": image.fov_revision,
        "url": url,
    }


def _snapshot_payload(db: Session, snapshot: Snapshot, storage) -> dict:
    images = db.scalars(
        select(SnapshotImage)
        .where(SnapshotImage.snapshot_id == snapshot.id)
        .order_by(SnapshotImage.camera_name_snapshot)
    ).all()
    attempts = db.scalars(
        select(AnalysisAttempt)
        .where(AnalysisAttempt.snapshot_id == snapshot.id)
        .order_by(AnalysisAttempt.attempt_number)
    ).all()
    return {
        "id": snapshot.id,
        "object_id": snapshot.object_id,
        "observed_at": snapshot.observed_at,
        "uploaded_at": snapshot.uploaded_at,
        "state": snapshot.state,
        "control_slot": snapshot.control_slot,
        "source": snapshot.source,
        "plan_snapshot": snapshot.plan_snapshot,
        "images": [_image_payload(image, storage) for image in images],
        "attempts": [_attempt_payload(attempt) for attempt in attempts],
    }


@router.post(
    "/objects/{object_id}/snapshots",
    response_model=SnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_snapshot(
    object_id: str,
    payload: SnapshotCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SnapshotResponse:
    object_item = owned_object(db, user, object_id)
    observed_at = datetime.combine(
        payload.observed_date,
        time.fromisoformat(payload.observed_time),
    )
    duplicate = db.scalar(
        select(Snapshot).where(
            Snapshot.object_id == object_id,
            Snapshot.observed_at == observed_at,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Проверка на эту дату и время уже существует")
    snapshot = Snapshot(
        object_id=object_id,
        observed_at=observed_at,
        state="draft",
        control_slot=nearest_control_slot(
            current_schedule(db, object_id, payload.observed_date).times,
            payload.observed_time,
        ),
        source=payload.source,
        plan_snapshot=build_plan_snapshot(db, object_item, payload.observed_date),
    )
    db.add(snapshot)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Проверка на эту дату и время уже существует") from exc
    return SnapshotResponse.model_validate(_snapshot_payload(db, snapshot, request.app.state.storage))


@router.post(
    "/snapshots/{snapshot_id}/images",
    response_model=SnapshotImageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_snapshot_image(
    snapshot_id: str,
    request: Request,
    camera_id: str = Form(),
    source: str = Form(default="manual"),
    file: UploadFile = File(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SnapshotImageResponse:
    snapshot = owned_snapshot(db, user, snapshot_id)
    if snapshot.state != "draft":
        raise HTTPException(status_code=409, detail="Снимки можно менять только до запуска анализа")
    camera = owned_camera(db, user, camera_id)
    if camera.object_id != snapshot.object_id or not camera.is_active:
        raise HTTPException(status_code=422, detail="Камера не принадлежит этой проверке")
    if source not in {"manual", "camera"}:
        raise HTTPException(status_code=422, detail="Неизвестное происхождение снимка")
    body = await file.read(MAX_IMAGE_BYTES + 1)
    content_type, extension = _validate_image(body)
    existing = db.scalar(
        select(SnapshotImage).where(
            SnapshotImage.snapshot_id == snapshot.id,
            SnapshotImage.camera_id == camera.id,
        )
    )
    image_id = existing.id if existing else new_id()
    relative_key = f"snapshots/{snapshot.object_id}/{snapshot.id}/{image_id}.{extension}"
    try:
        stored = request.app.state.storage.put(relative_key, body, content_type)
    except StorageError as exc:
        raise HTTPException(status_code=503, detail="Не удалось сохранить изображение") from exc

    old_key = existing.storage_key if existing else None
    image = existing or SnapshotImage(
        id=image_id,
        snapshot_id=snapshot.id,
        camera_id=camera.id,
        storage_key=stored.key,
        original_name=file.filename or f"{camera.code}.{extension}",
        content_type=content_type,
        byte_size=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        source=source,
        camera_name_snapshot=camera.name,
        camera_zone_snapshot=camera.zone,
        fov_revision=camera.fov_revision,
    )
    image.storage_key = stored.key
    image.original_name = file.filename or f"{camera.code}.{extension}"
    image.content_type = content_type
    image.byte_size = len(body)
    image.sha256 = hashlib.sha256(body).hexdigest()
    image.source = source
    image.camera_name_snapshot = camera.name
    image.camera_zone_snapshot = camera.zone
    image.fov_revision = camera.fov_revision
    db.add(image)
    db.commit()
    if old_key and old_key != stored.key:
        try:
            request.app.state.storage.delete(old_key)
        except StorageError:
            pass
    return SnapshotImageResponse.model_validate(_image_payload(image, request.app.state.storage))


@router.delete("/snapshot-images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_snapshot_image(
    image_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    image = owned_snapshot_image(db, user, image_id)
    snapshot = db.get(Snapshot, image.snapshot_id)
    if snapshot is None or snapshot.state != "draft":
        raise HTTPException(status_code=409, detail="Снимки можно менять только до запуска анализа")
    try:
        request.app.state.storage.delete(image.storage_key)
    except StorageError:
        pass
    db.delete(image)
    db.commit()


@router.post("/snapshots/{snapshot_id}/analyze", response_model=AnalyzeResponse, status_code=202)
def analyze_snapshot(
    snapshot_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalyzeResponse:
    snapshot = owned_snapshot(db, user, snapshot_id)
    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()
        if not idempotency_key or len(idempotency_key) > 128:
            raise HTTPException(
                status_code=422,
                detail="Идентификатор запуска должен содержать от 1 до 128 символов",
            )
    image_count = db.scalar(
        select(func.count(SnapshotImage.id)).where(SnapshotImage.snapshot_id == snapshot.id)
    ) or 0
    if image_count < 1:
        raise HTTPException(status_code=422, detail="Добавьте хотя бы одно корректное изображение")
    if idempotency_key:
        existing = db.scalar(
            select(AnalysisAttempt).where(
                AnalysisAttempt.snapshot_id == snapshot.id,
                AnalysisAttempt.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return AnalyzeResponse(
                snapshot_id=snapshot.id,
                state=existing.state,
                attempt_id=existing.id,
                attempt_number=existing.attempt_number,
            )
    running = db.scalar(
        select(AnalysisAttempt).where(
            AnalysisAttempt.snapshot_id == snapshot.id,
            AnalysisAttempt.state.in_(["queued", "analyzing"]),
        )
    )
    if running is not None:
        return AnalyzeResponse(
            snapshot_id=snapshot.id,
            state=running.state,
            attempt_id=running.id,
            attempt_number=running.attempt_number,
        )
    config = provider_config(request.app.state.settings)
    next_number = (
        db.scalar(
            select(func.max(AnalysisAttempt.attempt_number)).where(
                AnalysisAttempt.snapshot_id == snapshot.id
            )
        )
        or 0
    ) + 1
    attempt = AnalysisAttempt(
        snapshot_id=snapshot.id,
        attempt_number=next_number,
        state="queued",
        provider=config.provider,
        model=config.model,
        prompt_version=PROMPT_VERSION,
        idempotency_key=idempotency_key,
    )
    db.add(attempt)
    snapshot.state = "queued"
    db.commit()
    background_tasks.add_task(
        run_analysis_job,
        request.app.state.session_factory,
        request.app.state.storage,
        request.app.state.settings,
        snapshot.id,
        attempt.id,
    )
    return AnalyzeResponse(
        snapshot_id=snapshot.id,
        state=snapshot.state,
        attempt_id=attempt.id,
        attempt_number=attempt.attempt_number,
    )


@router.get("/snapshots/{snapshot_id}", response_model=SnapshotResponse)
def get_snapshot(
    snapshot_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SnapshotResponse:
    snapshot = owned_snapshot(db, user, snapshot_id)
    return SnapshotResponse.model_validate(_snapshot_payload(db, snapshot, request.app.state.storage))


@router.delete("/snapshots/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_draft_snapshot(
    snapshot_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    snapshot = owned_snapshot(db, user, snapshot_id)
    if snapshot.state != "draft":
        raise HTTPException(status_code=409, detail="Можно удалить только незапущенную проверку")
    images = db.scalars(
        select(SnapshotImage).where(SnapshotImage.snapshot_id == snapshot.id)
    ).all()
    for image in images:
        try:
            request.app.state.storage.delete(image.storage_key)
        except StorageError:
            pass
    db.delete(snapshot)
    db.commit()


@router.get("/objects/{object_id}/snapshots", response_model=List[SnapshotResponse])
@router.get("/objects/{object_id}/history", response_model=List[SnapshotResponse])
def list_snapshots(
    object_id: str,
    request: Request,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    camera_id: Optional[str] = None,
    source: Optional[str] = None,
    state: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[SnapshotResponse]:
    owned_object(db, user, object_id)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="Начало периода позже окончания")
    if source and source not in {"manual", "camera"}:
        raise HTTPException(status_code=422, detail="Неизвестное происхождение снимка")
    if state and state not in {
        "draft",
        "queued",
        "analyzing",
        "completed",
        "partial",
        "error",
    }:
        raise HTTPException(status_code=422, detail="Неизвестное состояние анализа")
    query = select(Snapshot).where(Snapshot.object_id == object_id)
    if date_from:
        query = query.where(Snapshot.observed_at >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.where(
            Snapshot.observed_at < datetime.combine(date_to + timedelta(days=1), time.min)
        )
    if camera_id:
        query = query.where(
            Snapshot.images.any(SnapshotImage.camera_id == camera_id)
        )
    if source:
        query = query.where(Snapshot.images.any(SnapshotImage.source == source))
    if state:
        query = query.where(Snapshot.state == state)
    rows = db.scalars(
        query.order_by(Snapshot.observed_at.desc(), Snapshot.uploaded_at.desc())
    ).all()
    return [
        SnapshotResponse.model_validate(_snapshot_payload(db, snapshot, request.app.state.storage))
        for snapshot in rows
    ]


@router.get("/images/{image_id}", response_model=SnapshotImageResponse)
def get_image(
    image_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SnapshotImageResponse:
    image = owned_snapshot_image(db, user, image_id)
    return SnapshotImageResponse.model_validate(_image_payload(image, request.app.state.storage))
