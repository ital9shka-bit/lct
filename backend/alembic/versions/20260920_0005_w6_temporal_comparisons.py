"""W6 temporal comparisons.

Revision ID: 20260920_0005
Revises: 20260920_0004
"""

from alembic import op
import sqlalchemy as sa


revision = "20260920_0005"
down_revision = "20260920_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "temporal_comparisons",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("camera_id", sa.String(length=36), nullable=False),
        sa.Column("first_image_id", sa.String(length=36), nullable=False),
        sa.Column("second_image_id", sa.String(length=36), nullable=False),
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
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["camera_id"], ["cameras.id"]),
        sa.ForeignKeyConstraint(["first_image_id"], ["snapshot_images.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["object_id"], ["objects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["second_image_id"], ["snapshot_images.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "first_image_id",
            "second_image_id",
            name="uq_temporal_comparison_image_pair",
        ),
    )
    op.create_index(
        op.f("ix_temporal_comparisons_object_id"),
        "temporal_comparisons",
        ["object_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_temporal_comparisons_camera_id"),
        "temporal_comparisons",
        ["camera_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_temporal_comparisons_first_image_id"),
        "temporal_comparisons",
        ["first_image_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_temporal_comparisons_second_image_id"),
        "temporal_comparisons",
        ["second_image_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_temporal_comparisons_state"),
        "temporal_comparisons",
        ["state"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("temporal_comparisons")
