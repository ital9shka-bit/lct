"""W3 snapshot idempotency and duplicate protection.

Revision ID: 20260920_0003
Revises: 20260919_0002
Create Date: 2026-09-20
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260920_0003"
down_revision: Union[str, None] = "20260919_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("analysis_attempts") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))
        batch.create_unique_constraint(
            "uq_attempt_snapshot_idempotency",
            ["snapshot_id", "idempotency_key"],
        )
    with op.batch_alter_table("snapshots") as batch:
        batch.create_unique_constraint(
            "uq_snapshot_object_observed",
            ["object_id", "observed_at"],
        )


def downgrade() -> None:
    with op.batch_alter_table("snapshots") as batch:
        batch.drop_constraint("uq_snapshot_object_observed", type_="unique")
    with op.batch_alter_table("analysis_attempts") as batch:
        batch.drop_constraint("uq_attempt_snapshot_idempotency", type_="unique")
        batch.drop_column("idempotency_key")
