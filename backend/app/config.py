from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "СтройКонтроль"
    environment: str = "development"
    database_url: str = "sqlite:///./stroykontrol.db"
    frontend_origins: str = "http://127.0.0.1:4173,http://localhost:4173"

    session_cookie_name: str = "stroykontrol_session"
    session_ttl_hours: int = 168
    session_cookie_secure: bool = False

    demo_login: str = "demo"
    demo_password: str = "demo"
    demo_email: str = "demo@demo.stroykontrol.ru"
    # Период демонстрации: этапы демо-плана идут в эти даты, демо-день переносится на «сегодня».
    demo_period_start: date = date(2026, 9, 29)
    demo_period_end: date = date(2026, 10, 15)

    registration_limit_count: int = 5
    registration_limit_window_seconds: int = 900

    s3_enabled: bool = False
    s3_endpoint: str = "http://minio:9000"
    s3_presign_endpoint: str = ""
    s3_region: str = "us-east-1"
    s3_bucket: str = "stroykontrol-dev"
    s3_prefix: str = "stroykontrol"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_presigned_ttl_seconds: int = 900

    mail_provider: str = "rusender"
    mail_enabled: bool = False
    rusender_base_url: str = "https://api.rusender.ru"
    rusender_api_key: str = ""
    rusender_key_id: str = ""
    mail_from: str = ""
    mail_from_name: str = "СтройКонтроль"
    mail_login_url: str = "http://127.0.0.1:4173/#/login"
    mail_technical_domain_note: str = ""

    ai_provider: str = "gatellm"
    ai_base_url: str = "https://gatellm.ru/v1"
    ai_api_key: str = ""
    ai_model: str = "openai/gpt-6-luna"
    ai_api_style: str = "chat_completions"
    ai_reasoning_effort: str = "low"
    ai_timeout_seconds: float = 90.0
    ai_image_max_edge: int = 1024
    ai_image_jpeg_quality: int = 75
    ai_input_price_per_million: Optional[float] = 0.20
    ai_output_price_per_million: Optional[float] = 1.20
    # Сколько раз подряд спрашивать одну модель при сбое провайдера или битом ответе.
    ai_attempts_per_model: int = 2
    # Резервная модель: подключается, когда основная исчерпала попытки.
    # Пустые поля наследуют значения основной модели; пустое имя модели отключает резерв.
    ai_fallback_model: str = "x-ai/grok-4.7"
    ai_fallback_provider: str = ""
    ai_fallback_base_url: str = ""
    ai_fallback_api_key: str = ""
    ai_fallback_api_style: str = ""
    ai_fallback_reasoning_effort: str = ""
    ai_fallback_input_price_per_million: Optional[float] = None
    ai_fallback_output_price_per_million: Optional[float] = None

    @field_validator("s3_prefix")
    @classmethod
    def normalize_s3_prefix(cls, value: str) -> str:
        normalized = value.strip().strip("/")
        if not normalized or normalized in {".", ".."} or ".." in normalized.split("/"):
            raise ValueError("S3_PREFIX must be a non-empty safe path prefix")
        return normalized

    @property
    def cors_origins(self) -> List[str]:
        return [item.strip() for item in self.frontend_origins.split(",") if item.strip()]

    def validate_s3_credentials(self) -> None:
        if self.s3_enabled and (not self.s3_access_key or not self.s3_secret_key):
            raise ValueError("S3 credentials are required when S3_ENABLED=true")


@lru_cache
def get_settings() -> Settings:
    return Settings()
