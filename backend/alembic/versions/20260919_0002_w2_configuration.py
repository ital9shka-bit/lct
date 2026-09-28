"""W2 object configuration, plan history and schedule versions.

Revision ID: 20260919_0002
Revises: 20260919_0001
Create Date: 2026-09-19
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260919_0002"
down_revision: Union[str, None] = "20260919_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cameras",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.add_column(
        "plan_items",
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "plan_items",
        sa.Column("is_outside_directory", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "plan_items",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "plan_items",
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.add_column(
        "plan_items",
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "object_schedules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("times", sa.JSON(), nullable=False),
        sa.Column("confirmation_threshold", sa.Integer(), nullable=False),
        sa.Column("absence_threshold", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["objects.id"],
            name=op.f("fk_object_schedules_object_id_objects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_object_schedules")),
        sa.UniqueConstraint("object_id", "version", name="uq_schedule_object_version"),
    )
    op.create_index(
        op.f("ix_object_schedules_effective_from"),
        "object_schedules",
        ["effective_from"],
    )
    op.create_index(
        op.f("ix_object_schedules_object_id"),
        "object_schedules",
        ["object_id"],
    )

    op.create_table(
        "plan_item_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("plan_item_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=32), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["objects.id"],
            name=op.f("fk_plan_item_revisions_object_id_objects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plan_item_id"],
            ["plan_items.id"],
            name=op.f("fk_plan_item_revisions_plan_item_id_plan_items"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plan_item_revisions")),
    )
    op.create_index(
        op.f("ix_plan_item_revisions_object_id"),
        "plan_item_revisions",
        ["object_id"],
    )
    op.create_index(
        op.f("ix_plan_item_revisions_plan_item_id"),
        "plan_item_revisions",
        ["plan_item_id"],
    )

    objects = sa.table("objects", sa.column("id", sa.String()))
    schedules = sa.table(
        "object_schedules",
        sa.column("id", sa.String()),
        sa.column("object_id", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("effective_from", sa.Date()),
        sa.column("times", sa.JSON()),
        sa.column("confirmation_threshold", sa.Integer()),
        sa.column("absence_threshold", sa.Integer()),
        sa.column("created_at", sa.DateTime()),
    )
    connection = op.get_bind()
    rows = connection.execute(sa.select(objects.c.id)).all()
    from datetime import date, datetime
    import uuid

    if rows:
        connection.execute(
            schedules.insert(),
            [
                {
                    "id": str(uuid.uuid4()),
                    "object_id": row.id,
                    "version": 1,
                    "effective_from": date(2026, 1, 1),
                    "times": ["09:00", "12:00", "15:00", "18:00"],
                    "confirmation_threshold": 2,
                    "absence_threshold": 3,
                    "created_at": datetime.utcnow(),
                }
                for row in rows
            ],
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_plan_item_revisions_plan_item_id"), table_name="plan_item_revisions")
    op.drop_index(op.f("ix_plan_item_revisions_object_id"), table_name="plan_item_revisions")
    op.drop_table("plan_item_revisions")
    op.drop_index(op.f("ix_object_schedules_object_id"), table_name="object_schedules")
    op.drop_index(op.f("ix_object_schedules_effective_from"), table_name="object_schedules")
    op.drop_table("object_schedules")
    op.drop_column("plan_items", "updated_at")
    op.drop_column("plan_items", "created_at")
    op.drop_column("plan_items", "sort_order")
    op.drop_column("plan_items", "is_outside_directory")
    op.drop_column("plan_items", "note")
    op.drop_column("cameras", "updated_at")
