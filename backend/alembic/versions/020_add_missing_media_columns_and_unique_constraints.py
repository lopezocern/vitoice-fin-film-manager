"""Add columns that only existed via the runtime auto-patcher, plus unique constraints.

Revision ID: 020
Revises: 019
Create Date: 2026-09-02

Context
-------
1. ``media.year`` / ``release_date`` / ``season_number`` / ``episode_number``
   are declared on the model but were never created by a migration. They only
   exist because ``app.database._ensure_additive_columns`` ALTERs them in at
   startup, which left ``alembic_version`` permanently out of sync with the
   models and produced un-indexed columns. This migration creates them
   **idempotently** (they are usually already present), so a fresh database and
   an existing patched database end up in the same state.

2. ``tags.name`` had no uniqueness guarantee, so the same name could be
   created repeatedly within one tag type. The constraint is
   ``(name, tag_type_id)`` — deliberately *not* ``name`` alone: the same
   performer legitimately exists as both an ``actor`` and an ``av_actress``
   tag, and the dev database has 18 such legitimate cross-type pairs.

3. ``media_libraries.root_path`` had no uniqueness guarantee, allowing the same
   directory to be registered twice and scanned into duplicate media rows.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (column name, type) — all nullable, matching the model declarations.
_MEDIA_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("year", sa.Integer()),
    ("release_date", sa.String(20)),
    ("season_number", sa.Integer()),
    ("episode_number", sa.Integer()),
)


def _existing_columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {c["name"] for c in inspector.get_columns(table)}


def _existing_indexes(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {i["name"] for i in inspector.get_indexes(table) if i["name"]}


def _has_unique_on(table: str, columns: Sequence[str]) -> bool:
    """True if a UNIQUE index already covers exactly `columns`.

    Catches the implicit `sqlite_autoindex_*` that batch_alter_table leaves
    behind, which `_existing_indexes` cannot see.
    """
    wanted = frozenset(columns)
    bind = op.get_bind()
    for row in bind.exec_driver_sql(f'PRAGMA index_list("{table}")').fetchall():
        name, is_unique = row[1], row[2]
        if not is_unique:
            continue
        cols = {
            r[2]
            for r in bind.exec_driver_sql(f'PRAGMA index_info("{name}")').fetchall()
        }
        if cols == wanted:
            return True
    return False


def upgrade() -> None:
    # 1. Backfill the four media columns, skipping any already patched in by
    #    _ensure_additive_columns so this migration is safe on both old and
    #    new databases.
    present = _existing_columns("media")
    indexes = _existing_indexes("media")
    for col_name, col_type in _MEDIA_COLUMNS:
        if col_name not in present:
            op.add_column("media", sa.Column(col_name, col_type, nullable=True))

    # Episode ordering is used by series navigation; index it once it exists.
    if "ix_media_season_episode" not in indexes and {
        "season_number",
        "episode_number",
    } <= (_existing_columns("media")):
        op.create_index(
            "ix_media_season_episode",
            "media",
            ["season_number", "episode_number"],
            unique=False,
        )

    # 2. Unique (name, tag_type_id) on tags.
    #    A plain UNIQUE INDEX rather than create_unique_constraint: the latter
    #    rebuilds the table and leaves an implicit `sqlite_autoindex_*` whose
    #    name we cannot control, making startup idempotency checks ambiguous.
    if "uq_tags_name_type" not in _existing_indexes("tags") and not _has_unique_on(
        "tags", ("name", "tag_type_id")
    ):
        op.create_index(
            "uq_tags_name_type", "tags", ["name", "tag_type_id"], unique=True
        )

    # 3. Unique root_path on media_libraries.
    if "uq_media_libraries_root_path" not in _existing_indexes(
        "media_libraries"
    ) and not _has_unique_on("media_libraries", ("root_path",)):
        op.create_index(
            "uq_media_libraries_root_path",
            "media_libraries",
            ["root_path"],
            unique=True,
        )


def downgrade() -> None:
    if "uq_media_libraries_root_path" in _existing_indexes("media_libraries"):
        op.drop_index("uq_media_libraries_root_path", table_name="media_libraries")
    if "uq_tags_name_type" in _existing_indexes("tags"):
        op.drop_index("uq_tags_name_type", table_name="tags")

    indexes = _existing_indexes("media")
    if "ix_media_season_episode" in indexes:
        op.drop_index("ix_media_season_episode", table_name="media")

    # The four columns are left in place on downgrade: dropping them would
    # destroy data on databases where they were patched in before this
    # migration ever ran.
