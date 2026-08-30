"""Add unique constraint on video_tags (media_id, tag_id).

Revision ID: 003
Revises: 002
Create Date: 2026-07-21

Deduplicates existing video_tags rows before adding the constraint so
the migration doesn't fail on pre-existing duplicates. Keeps the oldest
entry (lowest id) for each (media_id, tag_id) pair.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Remove duplicate video_tags entries, keeping the oldest (lowest id)
    op.execute("""
        DELETE FROM video_tags
        WHERE id NOT IN (
            SELECT MIN(id) FROM video_tags
            GROUP BY media_id, tag_id
        )
    """)

    # 2. Add unique constraint (batch mode for SQLite compatibility)
    with op.batch_alter_table("video_tags", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_video_tags_media_tag", ["media_id", "tag_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("video_tags", schema=None) as batch_op:
        batch_op.drop_constraint("uq_video_tags_media_tag", type_="unique")
