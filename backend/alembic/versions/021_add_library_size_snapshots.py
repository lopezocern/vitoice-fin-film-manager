"""add library_size_snapshots

容量趋势需要按天留点：只有"当前总大小"无法回答"哪个库上周涨了 200GB"。

Revision ID: 021
Revises: 020
Create Date: 2026-10-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "library_size_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column("captured_on", sa.Date(), nullable=False),
        sa.Column("media_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("missing_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.ForeignKeyConstraint(["library_id"], ["media_libraries.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_lib_size_snapshot_lib_day",
        "library_size_snapshots",
        ["library_id", "captured_on"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_lib_size_snapshot_lib_day", table_name="library_size_snapshots")
    op.drop_table("library_size_snapshots")
