from __future__ import annotations

from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analysis import provider_config
from ..database import get_db
from ..models import Camera, Snapshot, SnapshotImage, TemporalComparison, User
from ..movement import calculate_movement_signals
from ..schemas import (
    MovementSignalsResponse,
    TemporalComparisonCreate,
    TemporalComparisonResponse,
)
from ..storage import StorageError
from ..temporal import PROMPT_VERSION, run_comparison
from .dependencies import get_current_user
from .w2_common import owned_object


router = APIRouter(tags=["temporal-comparisons"])


def _comparison_image_payload(
    image: SnapshotImage, snapshot: Snapshot, storage
) -> dict:
    try:
        url = storage.presigned_get(image.storage_key)
    except StorageError:
        url = ""
    return {
        "id": image.id,
        "snapshot_id": snapshot.id,
        "observed_at": snapshot.observed_at,
        "camera_name": image.camera_name_snapshot,
        "camera_zone": image.camera_zone_snapshot,
        "fov_revision": image.fov_revision,
        "url": url,
    }


def comparison_payload(
    db: Session, item: TemporalComparison, storage
) -> TemporalComparisonResponse:
    first_image = db.get(SnapshotImage, item.first_image_id)
    second_image = db.get(SnapshotImage, item.second_image_id)
    first_snapshot = db.get(Snapshot, first_image.snapshot_id)
    second_snapshot = db.get(Snapshot, second_image.snapshot_id)
    return TemporalComparisonResponse.model_validate(
        {
            "id": item.id,
            "object_id": item.object_id,
            "camera_id": item.camera_id,
            "state": item.state,
            "provider": item.provider,
            "model": item.model,
            "prompt_version": item.prompt_version,
            "request_id": item.request_id,
            "duration_ms": item.duration_ms,
            "input_tokens": item.input_tokens,
            "output_tokens": item.output_tokens,
            "estimated_cost": item.estimated_cost,
            "result": item.result,
            "error_code": item.error_code,
            "error_detail": item.error_detail,
            "first_image": _comparison_image_payload(
                first_image, first_snapshot, storage
            ),
            "second_image": _comparison_image_payload(
                second_image, second_snapshot, storage
            ),
            "created_at": item.created_at,
            "finished_at": item.finished_at,
        }
    )


@router.post(
    "/objects/{object_id}/comparisons",
    response_model=TemporalComparisonResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_comparison(
    object_id: str,
    payload: TemporalComparisonCreate,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TemporalComparisonResponse:
    object_item = owned_object(db, user, object_id)
    if payload.first_image_id == payload.second_image_id:
        raise HTTPException(status_code=422, detail="Выберите два разных снимка")
    first_image = db.get(SnapshotImage, payload.first_image_id)
    second_image = db.get(SnapshotImage, payload.second_image_id)
    if first_image is None or second_image is None:
        raise HTTPException(status_code=404, detail="Снимок не найден")
    first_snapshot = db.get(Snapshot, first_image.snapshot_id)
    second_snapshot = db.get(Snapshot, second_image.snapshot_id)
    if (
        first_snapshot.object_id != object_id
        or second_snapshot.object_id != object_id
    ):
        raise HTTPException(status_code=404, detail="Снимок не найден")
    if (
        first_snapshot.state not in {"completed", "partial"}
        or second_snapshot.state not in {"completed", "partial"}
    ):
        raise HTTPException(
            status_code=422,
            detail="Сначала завершите анализ обоих снимков",
        )
    if first_image.camera_id != second_image.camera_id:
        raise HTTPException(
            status_code=422, detail="Сравнивать можно снимки одной камеры"
        )
    if first_image.fov_revision != second_image.fov_revision:
        raise HTTPException(
            status_code=422,
            detail="Между снимками менялся ракурс камеры",
        )
    if first_image.sha256 == second_image.sha256:
        raise HTTPException(
            status_code=422,
            detail="Повтор одного файла не подтверждает отсутствие перемещения",
        )
    if (first_snapshot.observed_at, first_image.id) > (
        second_snapshot.observed_at,
        second_image.id,
    ):
        first_image, second_image = second_image, first_image
        first_snapshot, second_snapshot = second_snapshot, first_snapshot

    existing = db.scalar(
        select(TemporalComparison).where(
            TemporalComparison.first_image_id == first_image.id,
            TemporalComparison.second_image_id == second_image.id,
        )
    )
    if existing is not None and existing.state != "error":
        return comparison_payload(db, existing, request.app.state.storage)
    if existing is not None:
        # Неудачное сравнение можно запустить заново: старая ошибка не блокирует пару.
        db.delete(existing)
        db.flush()

    camera = db.get(Camera, first_image.camera_id)
    config = provider_config(request.app.state.settings)
    item = TemporalComparison(
        object_id=object_id,
        camera_id=camera.id,
        first_image_id=first_image.id,
        second_image_id=second_image.id,
        state="analyzing",
        provider=config.provider,
        model=config.model,
        prompt_version=PROMPT_VERSION,
    )
    db.add(item)
    db.commit()
    run_comparison(
        db,
        request.app.state.storage,
        request.app.state.settings,
        item,
        object_item,
        camera,
        first_image,
        second_image,
        first_snapshot,
        second_snapshot,
    )
    return comparison_payload(db, item, request.app.state.storage)


@router.get(
    "/objects/{object_id}/comparisons",
    response_model=List[TemporalComparisonResponse],
)
def list_comparisons(
    object_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[TemporalComparisonResponse]:
    owned_object(db, user, object_id)
    rows = db.scalars(
        select(TemporalComparison)
        .where(TemporalComparison.object_id == object_id)
        .order_by(TemporalComparison.created_at.desc())
    ).all()
    return [comparison_payload(db, item, request.app.state.storage) for item in rows]


@router.get(
    "/objects/{object_id}/movement",
    response_model=MovementSignalsResponse,
)
def get_movement_signals(
    object_id: str,
    request: Request,
    date: date,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MovementSignalsResponse:
    owned_object(db, user, object_id)
    signals = calculate_movement_signals(db, object_id, date)
    for signal in signals:
        for image in signal["images"]:
            try:
                image["url"] = request.app.state.storage.presigned_get(
                    image.pop("storage_key")
                )
            except StorageError:
                image.pop("storage_key", None)
                image["url"] = ""
    return MovementSignalsResponse.model_validate(
        {"object_id": object_id, "date": date, "signals": signals}
    )
