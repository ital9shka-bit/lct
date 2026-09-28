from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import Engine

from .api import (
    auth,
    cameras,
    comparisons,
    health,
    inspections,
    mail,
    objects,
    plans,
    schedules,
    snapshots,
    stage_directory,
)
from .analysis import recover_interrupted_analyses
from .bootstrap import ensure_demo_account
from .config import Settings, get_settings
from .database import build_engine, build_session_factory
from .mail import DisabledMailSender, MailSender, RusenderMailSender
from .rate_limit import RegistrationRateLimiter
from .storage import DisabledStorage, S3Storage


def create_app(
    settings: Optional[Settings] = None,
    *,
    engine: Optional[Engine] = None,
    storage: Optional[Any] = None,
    mail_sender: Optional[MailSender] = None,
) -> FastAPI:
    settings = settings or get_settings()
    engine = engine or build_engine(settings)
    session_factory = build_session_factory(engine)
    storage = storage or (S3Storage(settings) if settings.s3_enabled else DisabledStorage())
    mail_sender = mail_sender or (
        RusenderMailSender(settings) if settings.mail_enabled else DisabledMailSender()
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ensure_demo_account(session_factory, settings)
        recover_interrupted_analyses(session_factory)
        if settings.s3_enabled:
            storage.ensure_ready()
        yield

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.storage = storage
    app.state.mail_sender = mail_sender
    app.state.registration_limiter = RegistrationRateLimiter(
        settings.registration_limit_count,
        settings.registration_limit_window_seconds,
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
            allow_headers=["Content-Type", "Idempotency-Key"],
        )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(objects.router)
    app.include_router(cameras.router)
    app.include_router(plans.router)
    app.include_router(schedules.router)
    app.include_router(snapshots.router)
    app.include_router(inspections.router)
    app.include_router(comparisons.router)
    app.include_router(stage_directory.router)
    app.include_router(mail.router)
    return app


app = create_app()
