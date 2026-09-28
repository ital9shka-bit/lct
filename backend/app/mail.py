from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Protocol

import httpx
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .models import WelcomeEmail


class MailDeliveryError(RuntimeError):
    pass


class MailSender(Protocol):
    def send_welcome(self, recipient: str, idempotency_key: str) -> str:
        ...


class DisabledMailSender:
    def send_welcome(self, recipient: str, idempotency_key: str) -> str:
        raise MailDeliveryError("Mail provider is not configured")


@dataclass
class RusenderMailSender:
    settings: Settings
    client: Optional[httpx.Client] = None

    def _html(self) -> str:
        note = ""
        if self.settings.mail_technical_domain_note:
            note = f"<p>{html.escape(self.settings.mail_technical_domain_note)}</p>"
        return (
            "<h1>Добро пожаловать в СтройКонтроль</h1>"
            "<p>Создайте объект, добавьте камеры и план работ, затем выполните проверку по фото.</p>"
            f'<p><a href="{html.escape(self.settings.mail_login_url, quote=True)}">Открыть СтройКонтроль</a></p>'
            + note
        )

    def send_welcome(self, recipient: str, idempotency_key: str) -> str:
        if not (
            self.settings.mail_enabled
            and self.settings.rusender_api_key
            and self.settings.rusender_key_id
            and self.settings.mail_from
        ):
            raise MailDeliveryError("Mail provider is not configured")
        payload = {
            "idempotencyKey": idempotency_key,
            "mail": {
                "to": {"email": recipient},
                "from": {
                    "email": self.settings.mail_from,
                    "name": self.settings.mail_from_name,
                },
                "subject": "Добро пожаловать в СтройКонтроль",
                "html": self._html(),
            },
        }
        client = self.client or httpx.Client(timeout=15.0)
        close_client = self.client is None
        try:
            response = client.post(
                f"{self.settings.rusender_base_url.rstrip('/')}/api/v1/external-mails/send/{self.settings.rusender_key_id}",
                headers={"Authorization": f"Bearer {self.settings.rusender_api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            message_id = data.get("uuid") if isinstance(data, dict) else None
            if not message_id:
                raise MailDeliveryError("RuSender response has no uuid")
            return str(message_id)
        except (httpx.HTTPError, ValueError) as exc:
            raise MailDeliveryError(f"RuSender request failed: {exc}") from exc
        finally:
            if close_client:
                client.close()


def deliver_welcome_email(
    session_factory: sessionmaker[Session], sender: MailSender, email_id: str
) -> None:
    with session_factory() as db:
        item = db.get(WelcomeEmail, email_id)
        if item is None or item.status == "sent":
            return
        item.status = "sending"
        item.attempts += 1
        item.last_attempt_at = datetime.utcnow()
        recipient = item.recipient
        # RuSender запоминает ответ по ключу, включая отказ: повтор с тем же ключом снова
        # получит 403, даже если ключ API уже активирован. Каждой попытке — свой ключ.
        idempotency_key = f"welcome-{item.id}-{item.attempts}"
        db.commit()

    try:
        provider_message_id = sender.send_welcome(recipient, idempotency_key)
    except Exception as exc:
        with session_factory() as db:
            item = db.get(WelcomeEmail, email_id)
            if item is not None:
                item.status = "failed"
                item.last_error = str(exc)[:2000]
                db.commit()
        return

    with session_factory() as db:
        item = db.get(WelcomeEmail, email_id)
        if item is not None:
            item.status = "sent"
            item.provider_message_id = provider_message_id
            item.last_error = None
            item.sent_at = datetime.utcnow()
            db.commit()

