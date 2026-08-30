"""Add series table and series aggregation columns on media.

Creates a `series` table to group TV episodes into show-level entities, and
adds `series_id` (FK) + `series_title` (fallback grouping key) to `media`.

Revision ID: 007
Revises: 006
Create Date: 2026-07-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create series table
    op.create_table(
        "series",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "library_id",
            sa.Integer(),
            sa.ForeignKey("media_libraries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("overview", sa.Text(), nullable=True),
        sa.Column("poster_path", sa.String(1000), nullable=True),
        sa.Column("scrape_data", sa.JSON(), nullable=True),
        sa.Column("total_seasons", sa.Integer(), nullable=True),
        sa.Column("total_episodes", sa.Integer(), nullable=True),
        sa.Column("episode_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_series_tmdb_id", "series", ["tmdb_id"])

    # 2. Add series columns to media — one column per batch_alter_table to
    #    avoid SQLite CircularDependencyError when adding multiple columns.
    with op.batch_alter_table("media", schema=None) as batch_op:
        batch_op.add_column(sa.Column("series_id", sa.Integer(), nullable=True))

    with op.batch_alter_table("media", schema=None) as batch_op:
        batch_op.add_column(sa.Column("series_title", sa.String(500), nullable=True))

    # 3. Add FK constraint (separate batch to avoid column-ordering issues)
    with op.batch_alter_table("media", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_media_series_id_series",
            "series",
            ["series_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_media_series_id", "media", ["series_id"])


def downgrade() -> None:
    op.drop_index("ix_media_series_id", table_name="media")
    with op.batch_alter_table("media", schema=None) as batch_op:
        batch_op.drop_column("series_title")
        batch_op.drop_column("series_id")
    op.drop_index("ix_series_tmdb_id", table_name="series")
    op.drop_table("series")
