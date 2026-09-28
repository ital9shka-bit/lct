"""W4 day rules, inspections and persisted evaluations.

Revision ID: 20260920_0004
Revises: 20260920_0003
Create Date: 2026-09-20
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260920_0004"
down_revision: Union[str, None] = "20260920_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inspections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("plan_item_id", sa.String(length=36), nullable=False),
        sa.Column("observed_date", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("verdict", sa.String(length=24), nullable=False),
        sa.Column("author", sa.String(length=160), nullable=False),
        sa.Column("role", sa.String(length=160), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["object_id"], ["objects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_item_id"], ["plan_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_inspections_object_id"), "inspections", ["object_id"])
    op.create_index(op.f("ix_inspections_plan_item_id"), "inspections", ["plan_item_id"])
    op.create_index(op.f("ix_inspections_observed_date"), "inspections", ["observed_date"])

    op.create_table(
        "inspection_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("inspection_id", sa.String(length=36), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["inspection_id"], ["inspections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        op.f("ix_inspection_attachments_inspection_id"),
        "inspection_attachments",
        ["inspection_id"],
    )
    op.create_index(
        op.f("ix_inspection_attachments_sha256"),
        "inspection_attachments",
        ["sha256"],
    )

    op.create_table(
        "day_evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("evaluation_date", sa.Date(), nullable=False),
        sa.Column("rules_version", sa.String(length=80), nullable=False),
        sa.Column("schedule_snapshot", sa.JSON(), nullable=False),
        sa.Column("plan_snapshot", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["object_id"], ["objects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_id", "evaluation_date", name="uq_day_evaluation_object_date"),
    )
    op.create_index(op.f("ix_day_evaluations_object_id"), "day_evaluations", ["object_id"])
    op.create_index(
        op.f("ix_day_evaluations_evaluation_date"),
        "day_evaluations",
        ["evaluation_date"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_day_evaluations_evaluation_date"), table_name="day_evaluations")
    op.drop_index(op.f("ix_day_evaluations_object_id"), table_name="day_evaluations")
    op.drop_table("day_evaluations")
    op.drop_index(op.f("ix_inspection_attachments_sha256"), table_name="inspection_attachments")
    op.drop_index(
        op.f("ix_inspection_attachments_inspection_id"),
        table_name="inspection_attachments",
    )
    op.drop_table("inspection_attachments")
    op.drop_index(op.f("ix_inspections_observed_date"), table_name="inspections")
    op.drop_index(op.f("ix_inspections_plan_item_id"), table_name="inspections")
    op.drop_index(op.f("ix_inspections_object_id"), table_name="inspections")
    op.drop_table("inspections")
