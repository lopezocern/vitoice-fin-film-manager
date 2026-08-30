"""Add global proxy settings (enabled switch + host + port).

Lets the user route vitoice's outbound requests (TMDB scraping, AV sources,
adult aggregator, AI tagging, URL checks, network-stream proxy) through an
HTTP proxy by configuring ip + port in Settings → 内容管理 (or 外部工具).

Revision ID: 015
Revises: 014
Create Date: 2026-08-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT OR IGNORE INTO settings (key, value, type, category, description)
        VALUES (
            'proxy_enabled',
            'false',
            'bool',
            'tools',
            'Route outbound requests (scraping, aggregator, AI) through an HTTP proxy. Off = direct connection.'
        )
    """)
    op.execute("""
        INSERT OR IGNORE INTO settings (key, value, type, category, description)
        VALUES (
            'proxy_host',
            '',
            'string',
            'tools',
            'Proxy host (IP or hostname).'
        )
    """)
    op.execute("""
        INSERT OR IGNORE INTO settings (key, value, type, category, description)
        VALUES (
            'proxy_port',
            '7890',
            'string',
            'tools',
            'Proxy port.'
        )
    """)


def downgrade() -> None:
    op.execute("DELETE FROM settings WHERE key IN ('proxy_enabled', 'proxy_host', 'proxy_port')")
