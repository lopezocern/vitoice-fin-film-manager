"""Add is_restricted column to media_libraries for content isolation.

Adds a boolean `is_restricted` field to the media_libraries table.
Libraries with scrape_mode='av' are automatically marked as restricted.
This field can be manually toggled per-library for any content type.

Revision ID: 009
Revises: 008
Create Date: 2026-07-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_restricted column (nullable first for safe backfill)
    op.add_column(
        "media_libraries",
        sa.Column("is_restricted", sa.Boolean(), nullable=True),
    )

    # Backfill: AV libraries default to restricted
    op.execute(
        "UPDATE media_libraries SET is_restricted = 1 WHERE scrape_mode = 'av'"
    )
    # All others default to not restricted
    op.execute(
        "UPDATE media_libraries SET is_restricted = 0 WHERE is_restricted IS NULL"
    )

    # Make NOT NULL now that all rows have values
    with op.batch_alter_table("media_libraries") as batch_op:
        batch_op.alter_column(
            "is_restricted",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        )


def downgrade() -> None:
    with op.batch_alter_table("media_libraries") as batch_op:
        batch_op.drop_column("is_restricted")
