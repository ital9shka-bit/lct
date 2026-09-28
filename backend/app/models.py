from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    sessions: Mapped[List["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    objects: Mapped[List["ConstructionObject"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="sessions")


class WelcomeEmail(Base):
    __tablename__ = "welcome_emails"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recipient: Mapped[str] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    provider_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ConstructionObject(Base):
    __tablename__ = "objects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    object_type: Mapped[str] = mapped_column(String(80), default="Жильё")
    address: Mapped[str] = mapped_column(String(500), default="")
    timezone: Mapped[str] = mapped_column(String(80), default="Europe/Moscow")
    is_draft: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Ключ объекта демо-набора (north, river, south); у обычных объектов пусто.
    demo_key: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    owner: Mapped[User] = relationship(back_populates="objects")
    cameras: Mapped[List["Camera"]] = relationship(back_populates="object", cascade="all, delete-orphan")
    plan_items: Mapped[List["PlanItem"]] = relationship(
        back_populates="object", cascade="all, delete-orphan"
    )
    schedules: Mapped[List["ObjectSchedule"]] = relationship(
        back_populates="object", cascade="all, delete-orphan"
    )
    snapshots: Mapped[List["Snapshot"]] = relationship(
        back_populates="object", cascade="all, delete-orphan"
    )
    inspections: Mapped[List["Inspection"]] = relationship(
        back_populates="object", cascade="all, delete-orphan"
    )
    day_evaluations: Mapped[List["DayEvaluation"]] = relationship(
        back_populates="object", cascade="all, delete-orphan"
    )


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (UniqueConstraint("object_id", "code", name="uq_camera_object_code"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    object_id: Mapped[str] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(80))
    zone: Mapped[str] = mapped_column(String(200), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    passport: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    fov_revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    object: Mapped[ConstructionObject] = relationship(back_populates="cameras")


class PlanItem(Base):
    __tablename__ = "plan_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    object_id: Mapped[str] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[Optional[str]] = mapped_column(ForeignKey("plan_items.id"), nullable=True)
    stage_code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    confirmation_method: Mapped[str] = mapped_column(String(24), default="cameras")
    observability: Mapped[str] = mapped_column(String(24), default="yes")
    camera_ids: Mapped[List[str]] = mapped_column(JSON, default=list)
    profile_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    is_outside_directory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    object: Mapped[ConstructionObject] = relationship(back_populates="plan_items")


class PlanItemRevision(Base):
    __tablename__ = "plan_item_revisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    object_id: Mapped[str] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    plan_item_id: Mapped[str] = mapped_column(ForeignKey("plan_items.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    event: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ObjectSchedule(Base):
    __tablename__ = "object_schedules"
    __table_args__ = (UniqueConstraint("object_id", "version", name="uq_schedule_object_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    object_id: Mapped[str] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    times: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    confirmation_threshold: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    absence_threshold: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    object: Mapped[ConstructionObject] = relationship(back_populates="schedules")


class Snapshot(Base):
    __tablename__ = "snapshots"
    __table_args__ = (UniqueConstraint("object_id", "observed_at", name="uq_snapshot_object_observed"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    object_id: Mapped[str] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    control_slot: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    source: Mapped[str] = mapped_column(String(24), default="manual")
    plan_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    object: Mapped[ConstructionObject] = relationship(back_populates="snapshots")
    images: Mapped[List["SnapshotImage"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    attempts: Mapped[List["AnalysisAttempt"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class SnapshotImage(Base):
    __tablename__ = "snapshot_images"
    __table_args__ = (UniqueConstraint("snapshot_id", "camera_id", name="uq_snapshot_camera"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"), index=True)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(24), default="manual")
    camera_name_snapshot: Mapped[str] = mapped_column(String(80))
    camera_zone_snapshot: Mapped[str] = mapped_column(String(200), default="")
    fov_revision: Mapped[int] = mapped_column(Integer, default=1)

    snapshot: Mapped[Snapshot] = relationship(back_populates="images")


class AnalysisAttempt(Base):
    __tablename__ = "analysis_attempts"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "idempotency_key", name="uq_attempt_snapshot_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(160))
    prompt_version: Mapped[str] = mapped_column(String(80))
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    raw_response: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    normalized_response: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    snapshot: Mapped[Snapshot] = relationship(back_populates="attempts")


class Inspection(Base):
    __tablename__ = "inspections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    object_id: Mapped[str] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    plan_item_id: Mapped[str] = mapped_column(ForeignKey("plan_items.id"), index=True)
    observed_date: Mapped[date] = mapped_column(Date, index=True)
    valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    verdict: Mapped[str] = mapped_column(String(24), nullable=False)
    author: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    object: Mapped[ConstructionObject] = relationship(back_populates="inspections")
    attachments: Mapped[List["InspectionAttachment"]] = relationship(
        back_populates="inspection", cascade="all, delete-orphan"
    )


class InspectionAttachment(Base):
    __tablename__ = "inspection_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    inspection_id: Mapped[str] = mapped_column(
        ForeignKey("inspections.id", ondelete="CASCADE"), index=True
    )
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)

    inspection: Mapped[Inspection] = relationship(back_populates="attachments")


class DayEvaluation(Base):
    __tablename__ = "day_evaluations"
    __table_args__ = (
        UniqueConstraint("object_id", "evaluation_date", name="uq_day_evaluation_object_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    object_id: Mapped[str] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    evaluation_date: Mapped[date] = mapped_column(Date, index=True)
    rules_version: Mapped[str] = mapped_column(String(80), nullable=False)
    schedule_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    plan_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    object: Mapped[ConstructionObject] = relationship(back_populates="day_evaluations")


class TemporalComparison(Base):
    __tablename__ = "temporal_comparisons"
    __table_args__ = (
        UniqueConstraint(
            "first_image_id",
            "second_image_id",
            name="uq_temporal_comparison_image_pair",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    object_id: Mapped[str] = mapped_column(
        ForeignKey("objects.id", ondelete="CASCADE"), index=True
    )
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), index=True)
    first_image_id: Mapped[str] = mapped_column(
        ForeignKey("snapshot_images.id", ondelete="CASCADE"), index=True
    )
    second_image_id: Mapped[str] = mapped_column(
        ForeignKey("snapshot_images.id", ondelete="CASCADE"), index=True
    )
    state: Mapped[str] = mapped_column(String(32), default="analyzing", index=True)
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(160))
    prompt_version: Mapped[str] = mapped_column(String(80))
    request_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    raw_response: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
