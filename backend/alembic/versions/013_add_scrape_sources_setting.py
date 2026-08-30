"""Add scrape_sources setting for unified scraping source chains.

Inserts a 'scrape_sources' JSON setting (category: scrape) into the
settings table. The value is a dict with three keys — movie / tv / av —
each holding an ordered list of source configs used as a fallback chain
by the scraper. Empty arrays mean "use the built-in defaults"
(TMDB from existing tmdb_* keys for movie/tv; JavBus→JavDB→JavLibrary
for av), so existing installs keep their current behavior.

Source config shape (per item):
    {
        "name": str,            # display name
        "kind": "tmdb"|"html",  # parser type (tmdb API vs html scraping)
        "base_url": str,        # endpoint / site root
        "image_base": str,      # poster image base (tmdb kind only)
        "api_key": str,         # api key (tmdb kind; empty inherits global tmdb_api_key)
        "language": str,        # search language (tmdb kind only)
        "timeout": int,         # request timeout seconds
        "enabled": bool         # participate in fallback chain
    }

Revision ID: 013
Revises: 012
Create Date: 2026-08-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEFAULT_SOURCES = '{"movie": [], "tv": [], "av": []}'


def upgrade() -> None:
    op.execute("""
        INSERT OR IGNORE INTO settings (key, value, type, category, description)
        VALUES (
            'scrape_sources',
            :value,
            'json',
            'scrape',
            'Unified scraping source chains (movie/tv/av). Empty arrays fall back to built-in defaults.'
        )
    """.replace(":value", "'" + _DEFAULT_SOURCES + "'"))


def downgrade() -> None:
    op.execute("DELETE FROM settings WHERE key = 'scrape_sources'")
