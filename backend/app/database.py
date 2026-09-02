"""Database engine and session management."""
from collections.abc import AsyncGenerator
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

_is_sqlite = "sqlite" in settings.database_url

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    # SQLite: disable thread check (async runs across threads) and set a
    # generous busy timeout (30s) so concurrent writers wait instead of
    # raising "database is locked" immediately.
    connect_args=(
        {"check_same_thread": False, "timeout": 30}
        if _is_sqlite
        else {}
    ),
    # SQLite: keep a small pool instead of a single connection. WAL mode lets
    # readers run concurrently with a single writer; writes are serialised by
    # SQLite's locking + the 30s busy timeout above, so a handful of pooled
    # connections is safe and prevents request starvation (a long video stream
    # on one connection would otherwise time out every other request).
    pool_size=3 if _is_sqlite else 5,
    max_overflow=2 if _is_sqlite else 10,
)


def apply_sqlite_pragmas(cursor, *, foreign_keys: bool = True) -> None:
    """Apply the project's standard SQLite pragmas to an open cursor.

    Shared by the engine's connect listener and by the test fixtures, so tests
    run under the same constraints as production (previously the fixtures built
    their own engine and silently ran with foreign_keys=OFF).

    Args:
        cursor: an open DBAPI cursor.
        foreign_keys: set to False for schema-rebuilding contexts (Alembic
            batch_alter requires foreign_keys=OFF while a table is recreated).
    """
    # Foreign key enforcement. SQLite defaults this to OFF **per connection**,
    # which silently disabled every `ondelete="CASCADE"` / `"SET NULL"`
    # declared on the models — only the ORM-level cascade fired, and bulk
    # `delete()` statements bypassed it entirely.
    if foreign_keys:
        cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")  # 30s
    cursor.execute("PRAGMA wal_autocheckpoint=1000")  # checkpoint every 1000 pages


# Enable WAL mode and tune pragmas for better concurrency on SQLite.
# WAL allows readers to proceed concurrently with a single writer.
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):  # noqa: D401
    if not _is_sqlite:
        return
    # aiosqlite wraps the raw sqlite3.Connection; the connect event may
    # receive either the raw connection or a wrapper. Use duck typing
    # (cursor() + execute) instead of isinstance to handle both cases.
    cursor = dbapi_conn.cursor()
    try:
        apply_sqlite_pragmas(cursor)
    finally:
        cursor.close()

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield an async session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _ensure_additive_columns(sync_conn) -> None:
    """Dev-mode guard: add nullable columns that exist on the models but not yet
    in the physical tables.

    `create_all()` only creates missing *tables*, never missing *columns* on an
    existing table. When the app evolves in dev mode (no Alembic run), newly
    added nullable columns would otherwise raise "no such column" at runtime.
    This helper issues idempotent `ALTER TABLE ADD COLUMN` for any missing
    column that is nullable or carries a default, so populated tables upgrade
    safely without a manual migration.
    """
    import logging
    from sqlalchemy import inspect as sa_inspect

    logger = logging.getLogger("vitoice")
    inspector = sa_inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all handles brand-new tables
        physical_cols = {c["name"] for c in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in physical_cols:
                continue
            # Only safe for populated tables when NULLs are allowed or a default
            # exists; skip NOT NULL columns without a default to avoid failures.
            has_default = col.default is not None or col.server_default is not None
            if not col.nullable and not has_default:
                logger.warning(
                    "Skipping auto-add of NOT NULL column %s.%s (needs migration)",
                    table.name, col.name,
                )
                continue
            col_type = col.type.compile(dialect=sync_conn.dialect)
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {col_type}'
            sync_conn.exec_driver_sql(ddl)
            logger.info("Auto-added missing column %s.%s", table.name, col.name)


# Unique indexes that must exist on every database, old or new.
#
# Why this is not handled by Alembic alone: the packaged app ships without
# alembic, and the production database has no `alembic_version` table at all —
# its schema is maintained by `create_all()` + `_ensure_additive_columns()`.
# `create_all()` never alters an existing table, so a constraint added to a
# model would silently be missing from every already-created database.
#
# These mirror migration 020; both paths are idempotent and converge.
_REQUIRED_UNIQUE_INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("uq_tags_name_type", "tags", ("name", "tag_type_id")),
    ("uq_media_libraries_root_path", "media_libraries", ("root_path",)),
)


def _existing_unique_column_sets(sync_conn, table: str) -> set[frozenset[str]]:
    """Return the column sets already covered by a UNIQUE index on `table`.

    Uses PRAGMA rather than SQLAlchemy's inspector because the latter omits
    SQLite's implicit `sqlite_autoindex_*` entries, which are exactly the ones
    Alembic's `create_unique_constraint` leaves behind.
    """
    sets: set[frozenset[str]] = set()
    try:
        indexes = sync_conn.exec_driver_sql(
            f'PRAGMA index_list("{table}")'
        ).fetchall()
    except Exception:  # noqa: BLE001 — table vanished / not SQLite
        return sets

    for row in indexes:
        # PRAGMA index_list -> (seq, name, unique, origin, partial)
        name, is_unique = row[1], row[2]
        if not is_unique or not name:
            continue
        try:
            cols = [
                r[2]
                for r in sync_conn.exec_driver_sql(
                    f'PRAGMA index_info("{name}")'
                ).fetchall()
            ]
        except Exception:  # noqa: BLE001
            continue
        if cols:
            sets.add(frozenset(cols))
    return sets


def _ensure_unique_constraints(sync_conn) -> None:
    """Idempotently create the unique indexes the models declare.

    A failure here must never prevent startup: duplicate rows can exist in
    databases created before the constraint, and forcing the issue would brick
    the app. Log loudly instead so the condition is visible.
    """
    import logging
    from sqlalchemy import inspect as sa_inspect

    logger = logging.getLogger("vitoice")
    inspector = sa_inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())

    for index_name, table, columns in _REQUIRED_UNIQUE_INDEXES:
        if table not in existing_tables:
            continue
        # Match on the *column set*, not the index name. Alembic's
        # create_unique_constraint produces an implicit `sqlite_autoindex_*`
        # whose name differs from ours while enforcing the same rule — keying
        # on the name would create a redundant duplicate index.
        if frozenset(columns) in _existing_unique_column_sets(sync_conn, table):
            continue

        cols = ", ".join(f'"{c}"' for c in columns)
        ddl = (
            f'CREATE UNIQUE INDEX IF NOT EXISTS "{index_name}" '
            f'ON "{table}" ({cols})'
        )
        try:
            sync_conn.exec_driver_sql(ddl)
            logger.info("Created unique index %s on %s", index_name, table)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not create unique index %s on %s (%s). "
                "Existing duplicate rows must be merged manually — see "
                "backend/tools/check_orphans.py for a duplicate scanner.",
                index_name,
                table,
                exc,
            )


async def init_db() -> None:
    """Ensure database is ready.

    If Alembic has already been run (alembic_version table exists), skip
    create_all() to avoid masking migration state. Otherwise, fall back to
    create_all() for dev convenience and warn that `alembic upgrade head`
    should be run to get seed data (default tag types + settings).

    In both paths, run the additive-column guard so nullable columns added to
    the models are backfilled onto existing tables without a manual migration.
    """
    from app.models import all_models  # noqa: F401 — register models on Base
    from sqlalchemy import inspect

    async with engine.begin() as conn:
        def _has_alembic_version(sync_conn) -> bool:
            return inspect(sync_conn).has_table("alembic_version")

        has_alembic = await conn.run_sync(_has_alembic_version)
        if not has_alembic:
            import logging
            logger = logging.getLogger("vitoice")
            logger.warning(
                "Database not migrated — running create_all() fallback. "
                "Run `alembic upgrade head` to apply migrations + seed data "
                "(default tag types, settings)."
            )
            await conn.run_sync(Base.metadata.create_all)

        # Backfill nullable columns onto existing tables (idempotent).
        await conn.run_sync(_ensure_additive_columns)
        # Backfill unique indexes declared on the models (idempotent).
        await conn.run_sync(_ensure_unique_constraints)
