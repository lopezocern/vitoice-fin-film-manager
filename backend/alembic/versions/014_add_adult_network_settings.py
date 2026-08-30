"""Add adult network source settings (allow switch + aggregator base URL).

Inserts two settings into the settings table:
- 'network_allow_adult' (bool, category: content, default false): master
  switch for the adult aggregator source resolver (javgg-style). When off,
  the resolve endpoint rejects requests and the frontend hides the entry.
- 'network_adult_base_url' (string, category: content, default javgg.net):
  root URL of the adult aggregator site. Domains rotate frequently, so the
  address is user-configurable instead of hardcoded.

Both settings are gated by show_restricted on the UI (hidden while the
"显示限制内容" toggle is off) to keep adult configuration isolated.

Revision ID: 014
Revises: 013
Create Date: 2026-08-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT OR IGNORE INTO settings (key, value, type, category, description)
        VALUES (
            'network_allow_adult',
            'false',
            'bool',
            'content',
            'Allow resolving adult aggregator network sources (javgg-style). When off, the resolver endpoint is disabled.'
        )
    """)
    op.execute("""
        INSERT OR IGNORE INTO settings (key, value, type, category, description)
        VALUES (
            'network_adult_base_url',
            'https://javgg.net',
            'string',
            'content',
            'Root URL of the adult aggregator site used for network source resolution.'
        )
    """)


def downgrade() -> None:
    op.execute("DELETE FROM settings WHERE key IN ('network_allow_adult', 'network_adult_base_url')")
