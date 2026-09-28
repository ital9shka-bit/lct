from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..mail import deliver_welcome_email
from ..models import User, WelcomeEmail
from ..schemas import WelcomeEmailListResponse, WelcomeEmailResponse
from .dependencies import get_current_user


router = APIRouter(prefix="/mail/welcome", tags=["mail"])


@router.get("", response_model=WelcomeEmailListResponse)
def list_welcome_emails(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> WelcomeEmailListResponse:
    items = db.scalars(
        select(WelcomeEmail)
        .where(WelcomeEmail.user_id == user.id)
        .order_by(WelcomeEmail.created_at.desc())
    ).all()
    return WelcomeEmailListResponse(
        items=[WelcomeEmailResponse.model_validate(item) for item in items]
    )


@router.post("/{email_id}/retry", response_model=WelcomeEmailResponse)
def retry_welcome_email(
    email_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WelcomeEmailResponse:
    item = db.scalar(
        select(WelcomeEmail).where(
            WelcomeEmail.id == email_id,
            WelcomeEmail.user_id == user.id,
        )
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Запись не найдена")
    if item.status == "sent":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Письмо уже отправлено")
    item.status = "pending"
    item.last_error = None
    db.commit()
    db.refresh(item)
    background_tasks.add_task(
        deliver_welcome_email,
        request.app.state.session_factory,
        request.app.state.mail_sender,
        item.id,
    )
    return WelcomeEmailResponse.model_validate(item)

