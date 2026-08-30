"""Add 'scrape' to TaskType enum for existing databases.

Revision ID: 002
Revises: 001
Create Date: 2026-07-21

SQLite stores sa.Enum as a VARCHAR with a CHECK constraint. Adding a new
enum value requires rebuilding the table via Alembic's batch mode (copy
data → drop old → rename new).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_VALUES = ["scan", "thumbnail", "metadata", "ai_tag", "subtitle", "hash"]
_NEW_VALUES = ["scan", "thumbnail", "metadata", "ai_tag", "subtitle", "hash", "scrape"]


def upgrade() -> None:
    # recreate='always' forces a table rebuild so the CHECK constraint
    # is updated with the new enum value. Without this, Alembic may skip
    # the rebuild because the storage type (VARCHAR) is unchanged.
    with op.batch_alter_table("tasks", schema=None, recreate="always") as batch_op:
        batch_op.alter_column(
            "type",
            existing_type=sa.Enum(*_OLD_VALUES, name="tasktype"),
            type_=sa.Enum(*_NEW_VALUES, name="tasktype"),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("tasks", schema=None, recreate="always") as batch_op:
        batch_op.alter_column(
            "type",
            existing_type=sa.Enum(*_NEW_VALUES, name="tasktype"),
            type_=sa.Enum(*_OLD_VALUES, name="tasktype"),
            existing_nullable=False,
        )
