"""Add the actual last playback timestamp to media.

Revision ID: 018
Revises: 017
Create Date: 2026-08-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("media", sa.Column("last_played_at", sa.DateTime(), nullable=True))
    op.create_index("ix_media_last_played_at", "media", ["last_played_at"], unique=False)
    # Preserve existing continue-watching entries during upgrade. Future
    # updates use the actual playback timestamp written by the progress API.
    op.execute(
        "UPDATE media SET last_played_at = updated_at "
        "WHERE playback_position > 0 AND last_played_at IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_media_last_played_at", table_name="media")
    op.drop_column("media", "last_played_at")
