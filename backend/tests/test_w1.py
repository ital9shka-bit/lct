from __future__ import annotations

from typing import Optional

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from backend.app.config import Settings
from backend.app.database import Base
from backend.app.mail import MailDeliveryError, RusenderMailSender
from backend.app.main import create_app
from backend.app.models import ConstructionObject, User, WelcomeEmail
from backend.app.storage import S3Storage, StorageError


class HealthyStorage:
    def ensure_ready(self) -> None:
        return None

    def healthcheck(self) -> str:
        return "ok"


class ToggleMailSender:
    def __init__(self, failing: bool = False) -> None:
        self.failing = failing
        self.calls: list[tuple[str, str]] = []

    def send_welcome(self, recipient: str, idempotency_key: str) -> str:
        self.calls.append((recipient, idempotency_key))
        if self.failing:
            raise MailDeliveryError("provider unavailable")
        return f"message-{len(self.calls)}"


@pytest.fixture
def engine():
    value = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(value)
    return value


def make_settings(**overrides) -> Settings:
    values = {
        "database_url": "sqlite://",
        "frontend_origins": "",
        "registration_limit_count": 100,
        "registration_limit_window_seconds": 60,
        "session_cookie_secure": False,
        "s3_enabled": False,
        "mail_enabled": False,
    }
    values.update(overrides)
    return Settings(**values)


def make_app(engine, sender: Optional[ToggleMailSender] = None, **settings):
    return create_app(
        make_settings(**settings),
        engine=engine,
        storage=HealthyStorage(),
        mail_sender=sender or ToggleMailSender(),
    )


def register(client: TestClient, email: str, password: str = "correct-horse"):
    return client.post("/auth/register", json={"email": email, "password": password})


def test_demo_login_cookie_me_logout_and_restart(engine) -> None:
    app = make_app(engine)
    with TestClient(app) as first:
        response = first.post("/auth/login", json={"identifier": "demo", "password": "demo"})
        assert response.status_code == 200
        assert response.json()["user"]["is_demo"] is True
        assert "httponly" in response.headers["set-cookie"].lower()
        raw_cookie = first.cookies.get("stroykontrol_session")
        assert raw_cookie
        assert first.get("/auth/me").status_code == 200

    restarted = make_app(engine)
    with TestClient(restarted) as second:
        second.cookies.set("stroykontrol_session", raw_cookie)
        assert second.get("/auth/me").status_code == 200
        logout = second.post("/auth/logout")
        assert logout.status_code == 204
        assert second.get("/auth/me").status_code == 401


def test_registration_is_immediate_hashed_and_duplicate_is_clear(engine) -> None:
    sender = ToggleMailSender(failing=True)
    app = make_app(engine, sender)
    with TestClient(app) as client:
        response = register(client, "new@example.org")
        assert response.status_code == 201
        assert response.json()["user"]["email"] == "new@example.org"
        assert client.get("/objects").json() == []
        assert register(client, "NEW@example.org").status_code == 409

        with app.state.session_factory() as db:
            user = db.scalar(select(User).where(User.email == "new@example.org"))
            message = db.scalar(select(WelcomeEmail).where(WelcomeEmail.user_id == user.id))
            assert user.password_hash.startswith("pbkdf2_sha256$")
            assert "correct-horse" not in user.password_hash
            assert message.status == "failed"
            assert message.attempts == 1

        assert client.post("/auth/logout").status_code == 204
        login = client.post(
            "/auth/login",
            json={"identifier": "new@example.org", "password": "correct-horse"},
        )
        assert login.status_code == 200


def test_mail_failure_can_be_retried_without_rolling_back_user(engine) -> None:
    sender = ToggleMailSender(failing=True)
    app = make_app(engine, sender)
    with TestClient(app) as client:
        assert register(client, "mail@example.org").status_code == 201
        failed = client.get("/mail/welcome").json()["items"][0]
        assert failed["status"] == "failed"
        sender.failing = False
        assert client.post(f"/mail/welcome/{failed['id']}/retry").status_code == 200
        sent = client.get("/mail/welcome").json()["items"][0]
        assert sent["status"] == "sent"
        assert sent["attempts"] == 2
        assert sent["provider_message_id"] == "message-2"


def test_object_list_is_isolated_by_authenticated_owner(engine) -> None:
    app = make_app(engine)
    with TestClient(app) as alice, TestClient(app) as bob:
        assert register(alice, "alice@example.org").status_code == 201
        assert register(bob, "bob@example.org").status_code == 201
        with app.state.session_factory() as db:
            users = {item.email: item for item in db.scalars(select(User)).all()}
            db.add_all(
                [
                    ConstructionObject(owner_id=users["alice@example.org"].id, name="Alice site"),
                    ConstructionObject(owner_id=users["bob@example.org"].id, name="Bob site"),
                ]
            )
            db.commit()
        assert [item["name"] for item in alice.get("/objects").json()] == ["Alice site"]
        assert [item["name"] for item in bob.get("/objects").json()] == ["Bob site"]


def test_registration_rate_limit_is_per_ip_and_returns_429(engine) -> None:
    app = make_app(engine, registration_limit_count=1)
    with TestClient(app) as client:
        assert register(client, "one@example.org").status_code == 201
        assert register(client, "two@example.org").status_code == 429


def test_rusender_payload_uses_bearer_key_id_and_idempotency() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        captured["body"] = request.read().decode()
        return httpx.Response(200, json={"uuid": "provider-uuid"})

    settings = make_settings(
        mail_enabled=True,
        rusender_api_key="test-api-key",
        rusender_key_id="key-id",
        mail_from="robot@example.org",
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        sender = RusenderMailSender(settings, client=http_client)
        assert sender.send_welcome("user@example.org", "welcome-1") == "provider-uuid"

    request = captured["request"]
    assert request.url.path == "/api/v1/external-mails/send/key-id"
    assert request.headers["authorization"] == "Bearer test-api-key"
    assert '"idempotencyKey":"welcome-1"' in captured["body"]
    assert '"email":"user@example.org"' in captured["body"]


class FakeS3Client:
    def __init__(self) -> None:
        self.calls = []
        self.list_pages = [
            {
                "Contents": [
                    {"Key": "stroykontrol/a.jpg"},
                    {"Key": "another-project/keep.jpg"},
                ],
                "IsTruncated": False,
            }
        ]

    def list_objects_v2(self, **kwargs):
        self.calls.append(("list", kwargs))
        if kwargs.get("MaxKeys") == 1:
            return {"Contents": [], "IsTruncated": False}
        return self.list_pages.pop(0)

    def put_object(self, **kwargs):
        self.calls.append(("put", kwargs))
        return {"ETag": "etag"}

    def generate_presigned_url(self, operation, Params, ExpiresIn):
        self.calls.append(("presign", {"operation": operation, **Params, "ttl": ExpiresIn}))
        return "http://signed.example/object"

    def delete_objects(self, **kwargs):
        self.calls.append(("delete", kwargs))
        return {}


def test_s3_storage_never_leaves_project_prefix() -> None:
    client = FakeS3Client()
    settings = make_settings(
        s3_enabled=True,
        s3_access_key="access",
        s3_secret_key="secret",
        s3_prefix="stroykontrol",
    )
    storage = S3Storage(settings, client=client)
    storage.ensure_ready()
    assert client.calls[-1] == (
        "list",
        {"Bucket": "stroykontrol-dev", "Prefix": "stroykontrol/", "MaxKeys": 1},
    )
    stored = storage.put("snapshots/image.jpg", b"image", "image/jpeg")
    assert stored.key == "stroykontrol/snapshots/image.jpg"
    assert storage.presigned_get("snapshots/image.jpg") == "http://signed.example/object"
    assert storage.presigned_get(stored.key) == "http://signed.example/object"
    with pytest.raises(StorageError):
        storage.put("../escape.jpg", b"image", "image/jpeg")

    deleted = storage.delete_project_objects()
    assert deleted == 1
    delete_call = [call for call in client.calls if call[0] == "delete"][0]
    assert delete_call[1]["Delete"]["Objects"] == [{"Key": "stroykontrol/a.jpg"}]
