"""W1 base schema.

Revision ID: 20260919_0001
Revises: None
Create Date: 2026-09-19
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260919_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_sessions_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
    )
    op.create_index(op.f("ix_user_sessions_expires_at"), "user_sessions", ["expires_at"])
    op.create_index(op.f("ix_user_sessions_token_hash"), "user_sessions", ["token_hash"], unique=True)
    op.create_index(op.f("ix_user_sessions_user_id"), "user_sessions", ["user_id"])

    op.create_table(
        "welcome_emails",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_welcome_emails_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_welcome_emails")),
    )
    op.create_index(op.f("ix_welcome_emails_status"), "welcome_emails", ["status"])
    op.create_index(op.f("ix_welcome_emails_user_id"), "welcome_emails", ["user_id"])

    op.create_table(
        "objects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("object_type", sa.String(length=80), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=False),
        sa.Column("timezone", sa.String(length=80), nullable=False),
        sa.Column("is_draft", sa.Boolean(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name=op.f("fk_objects_owner_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_objects")),
    )
    op.create_index(op.f("ix_objects_owner_id"), "objects", ["owner_id"])

    op.create_table(
        "cameras",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("zone", sa.String(length=200), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("passport", sa.JSON(), nullable=False),
        sa.Column("fov_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["object_id"], ["objects.id"], name=op.f("fk_cameras_object_id_objects"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cameras")),
        sa.UniqueConstraint("object_id", "code", name="uq_camera_object_code"),
    )
    op.create_index(op.f("ix_cameras_object_id"), "cameras", ["object_id"])

    op.create_table(
        "plan_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("stage_code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("confirmation_method", sa.String(length=24), nullable=False),
        sa.Column("observability", sa.String(length=24), nullable=False),
        sa.Column("camera_ids", sa.JSON(), nullable=False),
        sa.Column("profile_snapshot", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["object_id"], ["objects.id"], name=op.f("fk_plan_items_object_id_objects"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["plan_items.id"], name=op.f("fk_plan_items_parent_id_plan_items")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plan_items")),
    )
    op.create_index(op.f("ix_plan_items_object_id"), "plan_items", ["object_id"])

    op.create_table(
        "snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("control_slot", sa.String(length=16), nullable=True),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("plan_snapshot", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["object_id"], ["objects.id"], name=op.f("fk_snapshots_object_id_objects"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_snapshots")),
    )
    op.create_index(op.f("ix_snapshots_object_id"), "snapshots", ["object_id"])
    op.create_index(op.f("ix_snapshots_observed_at"), "snapshots", ["observed_at"])
    op.create_index(op.f("ix_snapshots_state"), "snapshots", ["state"])

    op.create_table(
        "snapshot_images",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("camera_id", sa.String(length=36), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("camera_name_snapshot", sa.String(length=80), nullable=False),
        sa.Column("camera_zone_snapshot", sa.String(length=200), nullable=False),
        sa.Column("fov_revision", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"], name=op.f("fk_snapshot_images_camera_id_cameras")),
        sa.ForeignKeyConstraint(["snapshot_id"], ["snapshots.id"], name=op.f("fk_snapshot_images_snapshot_id_snapshots"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_snapshot_images")),
        sa.UniqueConstraint("snapshot_id", "camera_id", name="uq_snapshot_camera"),
        sa.UniqueConstraint("storage_key", name=op.f("uq_snapshot_images_storage_key")),
    )
    op.create_index(op.f("ix_snapshot_images_camera_id"), "snapshot_images", ["camera_id"])
    op.create_index(op.f("ix_snapshot_images_sha256"), "snapshot_images", ["sha256"])
    op.create_index(op.f("ix_snapshot_images_snapshot_id"), "snapshot_images", ["snapshot_id"])

    op.create_table(
        "analysis_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("snapshot_id", sa.String(length=36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.String(length=64), nullable=True),
        sa.Column("raw_response", sa.JSON(), nullable=True),
        sa.Column("normalized_response", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["snapshot_id"], ["snapshots.id"], name=op.f("fk_analysis_attempts_snapshot_id_snapshots"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_attempts")),
    )
    op.create_index(op.f("ix_analysis_attempts_snapshot_id"), "analysis_attempts", ["snapshot_id"])
    op.create_index(op.f("ix_analysis_attempts_state"), "analysis_attempts", ["state"])


def downgrade() -> None:
    op.drop_index(op.f("ix_analysis_attempts_state"), table_name="analysis_attempts")
    op.drop_index(op.f("ix_analysis_attempts_snapshot_id"), table_name="analysis_attempts")
    op.drop_table("analysis_attempts")
    op.drop_index(op.f("ix_snapshot_images_snapshot_id"), table_name="snapshot_images")
    op.drop_index(op.f("ix_snapshot_images_sha256"), table_name="snapshot_images")
    op.drop_index(op.f("ix_snapshot_images_camera_id"), table_name="snapshot_images")
    op.drop_table("snapshot_images")
    op.drop_index(op.f("ix_snapshots_state"), table_name="snapshots")
    op.drop_index(op.f("ix_snapshots_observed_at"), table_name="snapshots")
    op.drop_index(op.f("ix_snapshots_object_id"), table_name="snapshots")
    op.drop_table("snapshots")
    op.drop_index(op.f("ix_plan_items_object_id"), table_name="plan_items")
    op.drop_table("plan_items")
    op.drop_index(op.f("ix_cameras_object_id"), table_name="cameras")
    op.drop_table("cameras")
    op.drop_index(op.f("ix_objects_owner_id"), table_name="objects")
    op.drop_table("objects")
    op.drop_index(op.f("ix_welcome_emails_user_id"), table_name="welcome_emails")
    op.drop_index(op.f("ix_welcome_emails_status"), table_name="welcome_emails")
    op.drop_table("welcome_emails")
    op.drop_index(op.f("ix_user_sessions_user_id"), table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_token_hash"), table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_expires_at"), table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
