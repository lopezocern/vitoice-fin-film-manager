"""Add metadata_ignored to media.

Revision ID: 019
Revises: 96c6cbc9d846
Create Date: 2026-08-19

Note (2026-09-02)
-----------------
Made idempotent. The column is usually **already present** because
``app.database._ensure_additive_columns`` ALTERs missing model columns in at
startup, long before anyone runs ``alembic upgrade``. The original version
issued an unconditional ``ADD COLUMN`` and therefore failed on any database
that had ever booted the app:

    sqlite3.OperationalError: duplicate column name: metadata_ignored

Any migration that adds a column this mechanism could have already created
must check first.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "96c6cbc9d846"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(table)}


def _existing_indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {i["name"] for i in inspector.get_indexes(table) if i["name"]}


def upgrade() -> None:
    if "metadata_ignored" not in _existing_columns("media"):
        op.add_column(
            "media",
            sa.Column(
                "metadata_ignored", sa.Boolean(), nullable=False, server_default="0"
            ),
        )
    if "ix_media_metadata_ignored" not in _existing_indexes("media"):
        op.create_index(
            "ix_media_metadata_ignored", "media", ["metadata_ignored"], unique=False
        )


def downgrade() -> None:
    if "ix_media_metadata_ignored" in _existing_indexes("media"):
        op.drop_index("ix_media_metadata_ignored", table_name="media")
    # The column is intentionally left in place: dropping it would destroy data
    # on databases where it was auto-added before this migration ever ran.
