"""Regression tests for SQLite foreign-key enforcement.

Background
-----------
`PRAGMA foreign_keys` defaults to OFF on every SQLite connection, so all
`ondelete="CASCADE"` / `"SET NULL"` declarations in the models were dead
letters at the database layer — only SQLAlchemy's ORM-level cascade fired, and
that is bypassed entirely by bulk `delete()` statements.

These tests pin the fix in `app/database.py::apply_sqlite_pragmas`. If someone
removes the pragma (or writes a new engine without wiring the listener), the
bulk-delete test below fails.
"""
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library import MediaLibrary
from app.models.media import Media
from app.models.segment import Segment
from app.models.series import Series
from app.models.tag import Tag, TagType

pytestmark = __import__("pytest").mark.asyncio


async def test_foreign_keys_pragma_is_enabled(db_session: AsyncSession) -> None:
    """The session's connection must report foreign_keys=ON."""
    result = await db_session.execute(text("PRAGMA foreign_keys"))
    assert result.scalar() == 1, (
        "PRAGMA foreign_keys is OFF — model-level ondelete rules are inert. "
        "Wire apply_sqlite_pragmas() into the engine's connect listener."
    )


async def test_orm_delete_media_cascades_children(db_session: AsyncSession) -> None:
    """ORM-level delete of a Media removes its segments."""
    lib = MediaLibrary(name="lib", root_path="/tmp/lib-fk-1")
    db_session.add(lib)
    await db_session.flush()

    media = Media(
        title="m", file_path="/tmp/m.mp4", file_name="m.mp4", library_id=lib.id
    )
    db_session.add(media)
    await db_session.flush()
    db_session.add(Segment(media_id=media.id, start_time=1.0, name="s1"))
    await db_session.flush()
    media_id = media.id

    await db_session.delete(media)
    await db_session.flush()

    remaining = (
        await db_session.execute(
            select(Segment).where(Segment.media_id == media_id)
        )
    ).scalars().all()
    assert remaining == []


async def test_bulk_delete_media_cascades_at_db_layer(
    db_session: AsyncSession,
) -> None:
    """Bulk DELETE bypasses the ORM cascade — the DB must do it.

    This is the test that actually proves `PRAGMA foreign_keys=ON`: a Core
    `delete()` statement issues plain SQL, so without DB enforcement the
    segment rows survive as orphans.
    """
    lib = MediaLibrary(name="lib", root_path="/tmp/lib-fk-2")
    db_session.add(lib)
    await db_session.flush()

    media = Media(
        title="m2", file_path="/tmp/m2.mp4", file_name="m2.mp4", library_id=lib.id
    )
    db_session.add(media)
    await db_session.flush()
    db_session.add(Segment(media_id=media.id, start_time=2.0, name="s2"))
    await db_session.flush()
    media_id = media.id

    # expire the identity map so nothing is loaded / cascaded by the ORM
    db_session.expunge_all()

    await db_session.execute(delete(Media).where(Media.id == media_id))
    await db_session.flush()

    remaining = (
        await db_session.execute(
            select(Segment).where(Segment.media_id == media_id)
        )
    ).scalars().all()
    assert remaining == [], (
        "Bulk delete left orphan segments — the DB-level ON DELETE CASCADE "
        "is not being enforced."
    )


async def test_bulk_delete_series_nulls_media_series_id(
    db_session: AsyncSession,
) -> None:
    """Deleting a Series must null out media.series_id, not orphan it."""
    lib = MediaLibrary(name="lib", root_path="/tmp/lib-fk-3")
    db_session.add(lib)
    await db_session.flush()

    series = Series(title="s", episode_count=1, library_id=lib.id)
    db_session.add(series)
    await db_session.flush()

    media = Media(
        title="m3",
        file_path="/tmp/m3.mp4",
        file_name="m3.mp4",
        library_id=lib.id,
        series_id=series.id,
    )
    db_session.add(media)
    await db_session.flush()
    series_id, media_id = series.id, media.id

    db_session.expunge_all()
    await db_session.execute(delete(Series).where(Series.id == series_id))
    await db_session.flush()

    row = (
        await db_session.execute(select(Media).where(Media.id == media_id))
    ).scalar_one()
    assert row.series_id is None


async def test_bulk_delete_parent_tag_nulls_children(
    db_session: AsyncSession,
) -> None:
    """Deleting a parent Tag must null out children.parent_id."""
    tag_type = TagType(name="tt-fk", is_builtin=False)
    db_session.add(tag_type)
    await db_session.flush()

    parent = Tag(name="parent", tag_type_id=tag_type.id)
    db_session.add(parent)
    await db_session.flush()
    child = Tag(name="child", tag_type_id=tag_type.id, parent_id=parent.id)
    db_session.add(child)
    await db_session.flush()
    parent_id, child_id = parent.id, child.id

    db_session.expunge_all()
    await db_session.execute(delete(Tag).where(Tag.id == parent_id))
    await db_session.flush()

    row = (await db_session.execute(select(Tag).where(Tag.id == child_id))).scalar_one()
    assert row.parent_id is None
