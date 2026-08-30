"""Add is_deleted and deleted_at columns to media for soft delete (recycle bin).

Revision ID: 005
Revises: 004
Create Date: 2026-07-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("media", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("deleted_at", sa.DateTime(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("media", schema=None) as batch_op:
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("is_deleted")
