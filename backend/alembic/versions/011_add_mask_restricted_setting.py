"""Add mask_restricted setting for content masking toggle.

Inserts a 'mask_restricted' boolean setting (default false) into the
settings table. When show_restricted is ON and mask_restricted is also ON,
restricted library posters and video frames are visually masked with a
blur overlay. This gives users control over whether to see restricted
content thumbnails or keep them masked.

Revision ID: 011
Revises: 010
Create Date: 2026-08-01
"""
from typing import Sequence, Union

from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT OR IGNORE INTO settings (key, value, type, category, description)
        VALUES (
            'mask_restricted',
            'false',
            'bool',
            'content',
            'Mask restricted content posters and video with blur overlay. Only effective when show_restricted is enabled.'
        )
    """)


def downgrade() -> None:
    op.execute("DELETE FROM settings WHERE key = 'mask_restricted'")
