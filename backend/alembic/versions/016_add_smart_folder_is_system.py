"""Add is_system flag to smart_folders for preset system folders.

System presets (全部媒体/继续观看/未看/...) are seeded idempotently by
app/api/smart_folders.py::init_system_folders on first list. This column
marks them so the frontend can hide delete/edit affordances.

Revision ID: 016
Revises: 015
Create Date: 2026-08-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "smart_folders",
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("smart_folders", "is_system")
