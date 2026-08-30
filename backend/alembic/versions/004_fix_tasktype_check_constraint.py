"""Force rebuild tasks table to fix TaskType CHECK constraint.

Revision ID: 004
Revises: 003
Create Date: 2026-07-21

Migration 002 used batch_alter_table without recreate='always', so the
CHECK constraint on the tasks.type column was not actually updated to
include 'scrape'. This migration forces a full table rebuild to fix
databases that already ran 002/003 without the constraint update.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FULL_VALUES = ["scan", "thumbnail", "metadata", "ai_tag", "subtitle", "hash", "scrape"]
_OLD_VALUES = ["scan", "thumbnail", "metadata", "ai_tag", "subtitle", "hash"]


def upgrade() -> None:
    # recreate='always' forces a copy-and-move table rebuild, which
    # regenerates the CHECK constraint with the full enum value list.
    with op.batch_alter_table("tasks", schema=None, recreate="always") as batch_op:
        batch_op.alter_column(
            "type",
            existing_type=sa.Enum(*_OLD_VALUES, name="tasktype"),
            type_=sa.Enum(*_FULL_VALUES, name="tasktype"),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("tasks", schema=None, recreate="always") as batch_op:
        batch_op.alter_column(
            "type",
            existing_type=sa.Enum(*_FULL_VALUES, name="tasktype"),
            type_=sa.Enum(*_OLD_VALUES, name="tasktype"),
            existing_nullable=False,
        )
