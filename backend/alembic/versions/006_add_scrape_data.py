"""Add scrape_data JSON column to media for full TMDB detail storage.

Revision ID: 006
Revises: 005
Create Date: 2026-07-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("media", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("scrape_data", sa.JSON(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("media", schema=None) as batch_op:
        batch_op.drop_column("scrape_data")
