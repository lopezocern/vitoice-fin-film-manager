"""add_unique_constraint_library_file

Revision ID: 96c6cbc9d846
Revises: 018
Create Date: 2026-08-16 16:49:29.596637

Defensive upgrade: dedupe existing (library_id, file_path) rows first —
legacy shadow records / path-separator variants would otherwise make
CREATE UNIQUE CONSTRAINT fail. Keeps the newest row per key; older
duplicates are soft-deleted (is_deleted=True, deleted_at=now) so no
metadata is physically lost.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text


revision: str = '96c6cbc9d846'
down_revision: Union[str, None] = '018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1) Normalize path separators so identical paths compare equal.
    conn.execute(
        text(
            "UPDATE media SET file_path = REPLACE(file_path, '/', '\\')"
            " WHERE file_path LIKE '%/%'"
        )
    )

    # 2) Soft-delete all but the newest row per (library_id, file_path).
    conn.execute(
        text(
            "UPDATE media SET is_deleted = 1, deleted_at = CURRENT_TIMESTAMP"
            " WHERE id NOT IN ("
            "   SELECT MAX(id) FROM media"
            "   WHERE file_path IS NOT NULL"
            "   GROUP BY library_id, file_path"
            " ) AND file_path IS NOT NULL"
            " AND id IN ("
            "   SELECT a.id FROM media a JOIN media b"
            "     ON a.library_id = b.library_id"
            "    AND a.file_path = b.file_path"
            "    AND a.id < b.id"
            " )"
        )
    )

    with op.batch_alter_table('media', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_media_library_file', ['library_id', 'file_path'])


def downgrade() -> None:
    with op.batch_alter_table('media', schema=None) as batch_op:
        batch_op.drop_constraint('uq_media_library_file', type_='unique')
