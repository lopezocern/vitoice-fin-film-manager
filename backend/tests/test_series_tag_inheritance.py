"""Tag sync inheritance test — TV episodes share the series tag set."""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base  # noqa: F401 (ensure models registered)
from app.models.enums import LibraryType, ScrapeMode
from app.models.library import MediaLibrary
from app.models.media import Media, VideoTag
from app.models.series import Series
from app.models.tag import Tag, TagType
from app.services.scraper import _sync_tags_for_media
from app.services.series_aggregator import _sync_tags_for_series


async def test_series_tag_inheritance_syncs_to_all_episodes(
    db_session: AsyncSession,
) -> None:
    lib = MediaLibrary(
        name="TV", type=LibraryType.VIDEO, root_path="C:/tv",
        scrape_mode=ScrapeMode.TV, is_restricted=False,
    )
    db_session.add(lib)
    await db_session.flush()

    show = Series(library_id=lib.id, title="Show", episode_count=2)
    db_session.add(show)
    await db_session.flush()

    ep1 = Media(library_id=lib.id, series_id=show.id, title="S01E01",
                file_name="s01e01.mkv", file_path="C:/tv/s01e01.mkv")
    ep2 = Media(library_id=lib.id, series_id=show.id, title="S01E02",
                file_name="s01e02.mkv", file_path="C:/tv/s01e02.mkv")
    db_session.add_all([ep1, ep2])
    await db_session.flush()

    # Scrape ep1 with two genre tags — should propagate to ep2.
    created = await _sync_tags_for_media(
        db_session, ep1.id, [("Drama", "genre"), ("Mystery", "genre")], source="scrape"
    )
    assert created >= 2
    await db_session.flush()

    result = await db_session.execute(
        select(VideoTag).where(VideoTag.media_id == ep2.id)
    )
    ep2_tags = {vt.tag_id for vt in result.scalars().all()}
    assert len(ep2_tags) == 2, f"ep2 should inherit both tags, got {ep2_tags}"

    result = await db_session.execute(
        select(VideoTag).where(VideoTag.media_id == ep1.id)
    )
    ep1_tags = {vt.tag_id for vt in result.scalars().all()}
    assert ep1_tags == ep2_tags, "ep1 and ep2 should share the same tag set"


async def test_tag_sync_skips_episodes_without_series(
    db_session: AsyncSession,
) -> None:
    lib = MediaLibrary(
        name="Movies", type=LibraryType.VIDEO, root_path="C:/movies",
        scrape_mode=ScrapeMode.MOVIE, is_restricted=False,
    )
    db_session.add(lib)
    await db_session.flush()

    movie = Media(library_id=lib.id, title="Movie", file_name="m.mkv",
                  file_path="C:/movies/m.mkv")
    db_session.add(movie)
    await db_session.flush()

    created = await _sync_tags_for_media(
        db_session, movie.id, [("SciFi", "genre")], source="scrape"
    )
    assert created == 1
    await db_session.flush()

    # No series → nothing else should be tagged beyond the movie itself.
    result = await db_session.execute(select(VideoTag))
    all_vt = list(result.scalars().all())
    assert len(all_vt) == 1
    assert all_vt[0].media_id == movie.id


async def test_series_tag_sync_fills_existing_episodes(
    db_session: AsyncSession,
) -> None:
    """存量数据补标：只有一集有标签时，系列同步应补到其他集。"""
    lib = MediaLibrary(
        name="TV", type=LibraryType.VIDEO, root_path="C:/tv",
        scrape_mode=ScrapeMode.TV, is_restricted=False,
    )
    db_session.add(lib)
    await db_session.flush()

    show = Series(library_id=lib.id, title="Old Show", episode_count=3)
    db_session.add(show)
    await db_session.flush()

    ep1 = Media(library_id=lib.id, series_id=show.id, title="S01E01",
                file_name="s01e01.mkv", file_path="C:/tv/s01e01.mkv")
    ep2 = Media(library_id=lib.id, series_id=show.id, title="S01E02",
                file_name="s01e02.mkv", file_path="C:/tv/s01e02.mkv")
    ep3 = Media(library_id=lib.id, series_id=show.id, title="S01E03",
                file_name="s01e03.mkv", file_path="C:/tv/s01e03.mkv")
    db_session.add_all([ep1, ep2, ep3])
    await db_session.flush()

    # 只有 ep1 有标签（模拟存量：直接插 VideoTag，绕过 scraper 的系列继承，
    # 这样才能测出 series sync 的"补标"作用）
    result = await db_session.execute(select(VideoTag).where(VideoTag.media_id == ep1.id))
    assert list(result.scalars().all()) == [], "ep1 should start without tags"
    # 找/建 Drama 标签
    result = await db_session.execute(select(Tag).where(Tag.name == "Drama"))
    drama = result.scalar_one_or_none()
    if drama is None:
        result = await db_session.execute(select(TagType).where(TagType.name == "genre"))
        genre_type = result.scalar_one_or_none()
        if genre_type is None:
            genre_type = TagType(name="genre", sort_order=1, is_builtin=True)
            db_session.add(genre_type)
            await db_session.flush()
        drama = Tag(name="Drama", tag_type_id=genre_type.id)
        db_session.add(drama)
        await db_session.flush()
    db_session.add(VideoTag(media_id=ep1.id, tag_id=drama.id, source="scrape"))
    await db_session.flush()

    # 前置检查：ep1 确实有 1 个标签，ep2/ep3 没有
    result = await db_session.execute(select(VideoTag).where(VideoTag.media_id == ep1.id))
    assert len(list(result.scalars().all())) == 1
    for ep in (ep2, ep3):
        result = await db_session.execute(select(VideoTag).where(VideoTag.media_id == ep.id))
        assert list(result.scalars().all()) == [], f"{ep.title} should start without tags"

    # 前置检查：series 与 episodes 可见
    result = await db_session.execute(select(Series.id).where(Series.library_id == lib.id))
    sid_rows = [row[0] for row in result.all()]
    assert sid_rows, f"series not found for lib {lib.id}"
    result = await db_session.execute(
        select(Media.id).where(Media.series_id == sid_rows[0])
    )
    ep_rows = [row[0] for row in result.all()]
    assert len(ep_rows) == 3, f"expected 3 episodes, got {len(ep_rows)}"

    # 系列标签同步：应把 Drama 补到 ep2/ep3
    synced = await _sync_tags_for_series(lib.id, session=db_session)
    await db_session.flush()
    assert synced >= 2

    for ep in (ep1, ep2, ep3):
        result = await db_session.execute(
            select(VideoTag).where(VideoTag.media_id == ep.id)
        )
        tags = {vt.tag_id for vt in result.scalars().all()}
        assert len(tags) == 1, f"episode {ep.title} should have 1 tag, got {tags}"
