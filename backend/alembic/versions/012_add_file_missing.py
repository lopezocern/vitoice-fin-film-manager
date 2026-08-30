"""Add file_missing and missing_detected_at columns to media table.

Also extends the media_type enum to include 'offline' for media whose
local file has been deleted but whose record is retained (with optional
network source fallback).

Revision ID: 012
Revises: 011
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add file_missing column (default False, indexed for fast filtering)
    op.add_column(
        "media",
        sa.Column("file_missing", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.create_index("ix_media_file_missing", "media", ["file_missing"])

    # Add missing_detected_at column (nullable, set when file loss is detected)
    op.add_column(
        "media",
        sa.Column("missing_detected_at", sa.DateTime(), nullable=True),
    )

    # Extend the media_type enum to include 'offline'.
    # SQLite doesn't enforce CHECK constraints on enum by default, so we
    # only need to ensure the application-level enum includes 'offline'.
    # For PostgreSQL we would ALTER TYPE, but SQLite is a no-op here.
    # The SQLAlchemy Enum with values_callable already handles the value.


def downgrade() -> None:
    op.drop_column("media", "missing_detected_at")
    op.drop_index("ix_media_file_missing", table_name="media")
    op.drop_column("media", "file_missing")
