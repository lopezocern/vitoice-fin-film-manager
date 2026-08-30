"""Add show_restricted setting for content isolation toggle.

Inserts a 'show_restricted' boolean setting (default false) into the
settings table. When false, media from restricted libraries is hidden
across all API endpoints. The backend restricted.py service reads this
value at query time.

Revision ID: 010
Revises: 009
Create Date: 2026-07-25
"""
from typing import Sequence, Union

from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT OR IGNORE INTO settings (key, value, type, category, description)
        VALUES (
            'show_restricted',
            'false',
            'bool',
            'content',
            'Show restricted content (AV/adult libraries). When off, restricted libraries are hidden from all views.'
        )
    """)


def downgrade() -> None:
    op.execute("DELETE FROM settings WHERE key = 'show_restricted'")
