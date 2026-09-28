from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .models import User
from .security import hash_password


def ensure_demo_account(session_factory: sessionmaker[Session], settings: Settings) -> User:
    with session_factory() as db:
        user = db.scalar(select(User).where(User.email == settings.demo_email.lower()))
        if user is None:
            user = User(
                email=settings.demo_email.lower(),
                password_hash=hash_password(settings.demo_password),
                is_demo=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        elif not user.is_demo:
            user.is_demo = True
            db.commit()
        return user

