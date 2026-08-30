"""Add metadata_ignored to media.

Revision ID: 019
Revises: 96c6cbc9d846
Create Date: 2026-08-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "96c6cbc9d846"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "media",
        sa.Column("metadata_ignored", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.create_index("ix_media_metadata_ignored", "media", ["metadata_ignored"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_media_metadata_ignored", table_name="media")
    op.drop_column("media", "metadata_ignored")