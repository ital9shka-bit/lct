"""Demo set key on objects.

Revision ID: 20260922_0006
Revises: 20260920_0005
"""

from alembic import op
import sqlalchemy as sa


revision = "20260922_0006"
down_revision = "20260920_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("objects", sa.Column("demo_key", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("objects", "demo_key")
