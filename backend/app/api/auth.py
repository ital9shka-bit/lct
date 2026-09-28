from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..mail import deliver_welcome_email
from ..models import User, UserSession, WelcomeEmail
from ..schemas import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from ..security import create_session, hash_password, hash_session_token, verify_password
from .dependencies import get_current_user


router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookie(response: Response, request: Request, token: str) -> None:
    settings = request.app.state.settings
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> AuthResponse:
    email = str(payload.email).strip().lower()
    client_ip = request.client.host if request.client else "unknown"
    limiter = request.app.state.registration_limiter
    if not limiter.allow(f"ip:{client_ip}") or not limiter.allow(f"email:{email}"):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Слишком много попыток")
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Адрес уже зарегистрирован")

    try:
        user = User(email=email, password_hash=hash_password(payload.password), is_demo=False)
        db.add(user)
        db.flush()
        welcome = WelcomeEmail(user_id=user.id, recipient=email, status="pending")
        db.add(welcome)
        _, raw_token = create_session(db, user, request.app.state.settings.session_ttl_hours)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Адрес уже зарегистрирован") from exc
    db.refresh(user)
    _set_cookie(response, request, raw_token)
    background_tasks.add_task(
        deliver_welcome_email,
        request.app.state.session_factory,
        request.app.state.mail_sender,
        welcome.id,
    )
    return AuthResponse(user=UserResponse.model_validate(user))


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthResponse:
    settings = request.app.state.settings
    identifier = payload.identifier.strip().lower()
    email = settings.demo_email.lower() if identifier == settings.demo_login.lower() else identifier
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Проверьте логин и пароль")
    _, raw_token = create_session(db, user, settings.session_ttl_hours)
    db.commit()
    _set_cookie(response, request, raw_token)
    if user.is_demo:
        _refresh_demo(request)
    return AuthResponse(user=UserResponse.model_validate(user))


def _refresh_demo(request: Request) -> None:
    """Демо-набор каждый день показа начинается с трёх готовых проверок на сегодня."""
    from ..demo_seed import ensure_demo_current

    ensure_demo_current(
        request.app.state.session_factory,
        request.app.state.storage,
        request.app.state.settings,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    settings = request.app.state.settings
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        session = db.scalar(
            select(UserSession).where(UserSession.token_hash == hash_session_token(raw_token))
        )
        if session is not None:
            db.delete(session)
            db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=AuthResponse)
def me(request: Request, user: User = Depends(get_current_user)) -> AuthResponse:
    if user.is_demo:
        _refresh_demo(request)
    return AuthResponse(user=UserResponse.model_validate(user))
