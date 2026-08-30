"""Add AV-specific tag types for tag isolation.

Creates dedicated tag types (av_actress, av_genre, av_studio, av_series,
av_director) to isolate AV metadata from movie/TV tags. Also migrates
existing AV-only tags from shared types to the new AV types.

Revision ID: 008
Revises: 007
Create Date: 2026-07-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Insert AV-specific tag types (idempotent — skip if already exists)
    op.execute("""
        INSERT OR IGNORE INTO tag_types (name, color, is_builtin, sort_order) VALUES
        ('av_actress',  '#af52de', 1, 10),
        ('av_genre',    '#ff3b30', 1, 11),
        ('av_studio',   '#5856D6', 1, 12),
        ('av_series',   '#007aff', 1, 13),
        ('av_director', '#5ac8fa', 1, 14)
    """)

    # 2. Migrate existing AV-only tags to AV tag types.
    #    A tag is "AV-only" if ALL its associated media belong to libraries
    #    with scrape_mode='av'. Tags shared between AV and non-AV media are
    #    left untouched (the user can re-scrape to split them).
    #
    #    Mapping: actor → av_actress, genre → av_genre, studio → av_studio,
    #             collection → av_series
    #    (director was previously stored as 'actor' — those become av_actress,
    #     which is acceptable; re-scraping will create proper av_director tags.)

    # Tags associated ONLY with AV library media
    op.execute("""
        UPDATE tags SET tag_type_id = (
            SELECT id FROM tag_types WHERE name = 'av_actress'
        )
        WHERE tag_type_id = (SELECT id FROM tag_types WHERE name = 'actor')
        AND id IN (
            SELECT DISTINCT vt.tag_id FROM video_tags vt
            JOIN media m ON m.id = vt.media_id
            JOIN media_libraries ml ON ml.id = m.library_id
            WHERE ml.scrape_mode = 'av'
        )
        AND id NOT IN (
            SELECT DISTINCT vt.tag_id FROM video_tags vt
            JOIN media m ON m.id = vt.media_id
            JOIN media_libraries ml ON ml.id = m.library_id
            WHERE ml.scrape_mode != 'av'
        )
    """)

    op.execute("""
        UPDATE tags SET tag_type_id = (
            SELECT id FROM tag_types WHERE name = 'av_genre'
        )
        WHERE tag_type_id = (SELECT id FROM tag_types WHERE name = 'genre')
        AND id IN (
            SELECT DISTINCT vt.tag_id FROM video_tags vt
            JOIN media m ON m.id = vt.media_id
            JOIN media_libraries ml ON ml.id = m.library_id
            WHERE ml.scrape_mode = 'av'
        )
        AND id NOT IN (
            SELECT DISTINCT vt.tag_id FROM video_tags vt
            JOIN media m ON m.id = vt.media_id
            JOIN media_libraries ml ON ml.id = m.library_id
            WHERE ml.scrape_mode != 'av'
        )
    """)

    op.execute("""
        UPDATE tags SET tag_type_id = (
            SELECT id FROM tag_types WHERE name = 'av_studio'
        )
        WHERE tag_type_id = (SELECT id FROM tag_types WHERE name = 'studio')
        AND id IN (
            SELECT DISTINCT vt.tag_id FROM video_tags vt
            JOIN media m ON m.id = vt.media_id
            JOIN media_libraries ml ON ml.id = m.library_id
            WHERE ml.scrape_mode = 'av'
        )
        AND id NOT IN (
            SELECT DISTINCT vt.tag_id FROM video_tags vt
            JOIN media m ON m.id = vt.media_id
            JOIN media_libraries ml ON ml.id = m.library_id
            WHERE ml.scrape_mode != 'av'
        )
    """)

    op.execute("""
        UPDATE tags SET tag_type_id = (
            SELECT id FROM tag_types WHERE name = 'av_series'
        )
        WHERE tag_type_id = (SELECT id FROM tag_types WHERE name = 'collection')
        AND id IN (
            SELECT DISTINCT vt.tag_id FROM video_tags vt
            JOIN media m ON m.id = vt.media_id
            JOIN media_libraries ml ON ml.id = m.library_id
            WHERE ml.scrape_mode = 'av'
        )
        AND id NOT IN (
            SELECT DISTINCT vt.tag_id FROM video_tags vt
            JOIN media m ON m.id = vt.media_id
            JOIN media_libraries ml ON ml.id = m.library_id
            WHERE ml.scrape_mode != 'av'
        )
    """)


def downgrade() -> None:
    # Move AV tags back to shared types
    type_mapping = {
        'av_actress': 'actor',
        'av_genre': 'genre',
        'av_studio': 'studio',
        'av_series': 'collection',
        'av_director': 'actor',
    }
    for av_name, shared_name in type_mapping.items():
        op.execute(f"""
            UPDATE tags SET tag_type_id = (
                SELECT id FROM tag_types WHERE name = '{shared_name}'
            )
            WHERE tag_type_id = (
                SELECT id FROM tag_types WHERE name = '{av_name}'
            )
        """)

    # Remove AV tag types
    op.execute("""
        DELETE FROM tag_types WHERE name IN (
            'av_actress', 'av_genre', 'av_studio', 'av_series', 'av_director'
        )
    """)
