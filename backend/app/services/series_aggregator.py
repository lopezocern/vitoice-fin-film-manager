"""Series aggregation service — groups TV episodes into Series entities.

Runs after library scan to pre-group episodes by parsed title, before TMDB
scraping upgrades the grouping to use tmdb_id. Also sets season_number and
episode_number on Media records parsed from filenames.

Flow:
    scan → aggregate_series (title-based grouping)
         → scrape_media (upgrades to tmdb_id-based grouping)

The aggregation is idempotent: re-running it won't create duplicate Series or
re-link already-linked media.

Parent-directory fallback:
    When a filename is just an episode marker (e.g. "第1集.mp4", "E05.mkv"),
    the parsed title is meaningless. In this case the aggregator falls back to
    the **parent directory name** to determine the series title and season.

    Examples:
        "庆余年 第一季/第1集.mp4"  → title="庆余年", season=1, episode=1
        "庆余年 第二季/第3集.mp4"  → title="庆余年", season=2, episode=3
        "Some Show/Season 2/E05.mkv" → title="Some Show", season=2, episode=5
"""
import logging
import re

from sqlalchemy import func, select

from app.database import async_session
from app.models.enums import ScrapeMode
from app.models.library import MediaLibrary
from app.models.media import Media
from app.models.series import Series
from app.models.tag import VideoTag
from app.services.scraper import parse_filename, _is_episode_marker_title, _parse_parent_dir_for_title

logger = logging.getLogger("vitoice.series_aggregator")


def _normalize_title(title: str) -> str:
    """Normalize a title for grouping comparison (lowercase, collapse spaces)."""
    return re.sub(r"\s+", " ", title.strip().lower())


async def cleanup_orphaned_series(library_id: int) -> int:
    """Remove Series records that have no active (non-deleted) media.

    After a library cleanup / re-import, stale Series records may linger
    with episode_count > 0 but no actual media pointing to them. This
    function recalculates episode counts and deletes orphans.

    Returns the number of Series deleted.
    """
    from sqlalchemy import delete

    async with async_session() as session:
        # Load all Series for this library
        result = await session.execute(
            select(Series).where(Series.library_id == library_id)
        )
        all_series = list(result.scalars().all())

        if not all_series:
            return 0

        # Batch query: count active media per series_id in a single SELECT
        # (replaces N+1 per-series COUNT queries)
        series_ids = [s.id for s in all_series]
        count_result = await session.execute(
            select(Media.series_id, func.count(Media.id))
            .where(
                Media.series_id.in_(series_ids),
                Media.is_deleted == False,  # noqa: E712
            )
            .group_by(Media.series_id)
        )
        actual_counts: dict[int, int] = {}
        for sid, cnt in count_result.fetchall():
            actual_counts[sid] = cnt

        deleted = 0
        for s in all_series:
            actual_count = actual_counts.get(s.id, 0)

            if actual_count == 0:
                logger.info("Deleting orphaned Series %s ('%s') — no active media", s.id, s.title)
                await session.delete(s)
                deleted += 1
            elif actual_count != s.episode_count:
                # Fix stale count
                s.episode_count = actual_count

        if deleted:
            await session.commit()

    return deleted


async def aggregate_series(library_id: int) -> int:
    """Aggregate media into Series entities based on parsed filenames.

    For each Media without a series_id:
    1. Parse filename to extract (title, year, season, episode)
    2. If the title is just an episode marker, fall back to parent directory
    3. If episode_number is not None, it's a TV episode
    4. Group by normalized title within the library
    5. Create/find Series and link media

    Also updates season_number and episode_number on Media records.
    Cleans up orphaned Series (no active media) before aggregating.

    Returns the number of Series created.
    """
    # Clean up orphaned Series from previous imports
    await cleanup_orphaned_series(library_id)

    series_created = 0

    async with async_session() as session:
        # Load library to check scrape_mode
        lib = await session.get(MediaLibrary, library_id)
        if not lib:
            raise ValueError(f"Library {library_id} not found")

        # Only aggregate for TV-mode libraries
        if lib.scrape_mode != ScrapeMode.TV:
            return 0

        # Load all non-deleted media without series_id in this library
        result = await session.execute(
            select(Media)
            .where(
                Media.library_id == library_id,
                Media.is_deleted == False,  # noqa: E712
                Media.series_id.is_(None),
            )
            .order_by(Media.file_name)
        )
        media_list = result.scalars().all()

        if not media_list:
            return 0

        # Parse filenames and group by normalized title
        # groups: {normalized_title: [(media, parsed_tuple), ...]}
        groups: dict[str, list[tuple[Media, tuple]]] = {}
        for media in media_list:
            parsed = parse_filename(media.file_name)
            title, year, season, episode = parsed

            # --- Parent directory fallback ---
            # When the filename is just an episode marker (e.g. "第1集.mp4"),
            # the parsed title is meaningless. Use the parent directory name
            # to determine the series title and possibly the season number.
            if episode is not None and _is_episode_marker_title(title):
                dir_title, dir_season = _parse_parent_dir_for_title(media.file_path)
                title = dir_title
                # Always prefer the directory's season over the default.
                # parse_filename sets season=1 for seasonless episodes, but
                # the directory may indicate a different season (e.g.
                # "庆余年 第二季" → season=2, not the default 1).
                if dir_season is not None:
                    season = dir_season
                # Also update the parsed tuple so year etc. propagate
                parsed = (title, year, season, episode)

            # Update season/episode on the media record (even if not grouping)
            if season is not None:
                media.season_number = season
            if episode is not None:
                media.episode_number = episode

            # Only group if this looks like a TV episode
            if episode is None:
                continue

            # Use the parsed title as series_title
            media.series_title = title
            norm = _normalize_title(title)
            if norm not in groups:
                groups[norm] = []
            groups[norm].append((media, parsed))

        if not groups:
            await session.commit()
            return 0

        # Load existing Series in this library (by normalized title) to avoid
        # duplicates — a Series may already exist from a previous scrape.
        existing_series: dict[str, Series] = {}
        result = await session.execute(
            select(Series).where(Series.library_id == library_id)
        )
        for s in result.scalars().all():
            existing_series[_normalize_title(s.title)] = s

        # Create/update Series for each group
        for norm_title, items in groups.items():
            # Use the first item's title (original casing) as the Series title
            series_title = items[0][0].series_title or items[0][1][0]

            existing = existing_series.get(norm_title)
            if existing:
                # Link media to existing Series (may have tmdb_id from prior scrape)
                for media, _ in items:
                    media.series_id = existing.id
                # Update episode count
                result = await session.execute(
                    select(func.count(Media.id)).where(
                        Media.series_id == existing.id,
                        Media.is_deleted == False,  # noqa: E712
                    )
                )
                existing.episode_count = result.scalar() or 0
            else:
                # Create new Series
                first_year = items[0][1][1]  # year from first parsed item
                new_series = Series(
                    library_id=library_id,
                    title=series_title,
                    year=first_year,
                    episode_count=len(items),
                )
                session.add(new_series)
                await session.flush()  # Get the ID

                existing_series[norm_title] = new_series
                series_created += 1

                # Link media to new Series
                for media, _ in items:
                    media.series_id = new_series.id

        await session.commit()

    # ---- 系列标签补同步 ----
    # 聚合（扫描）后把每个系列内已有标签求并集，统一同步到所有子剧集——
    # 覆盖"部分集刮削过有标签、其余集缺标签"的存量数据。
    await _sync_tags_for_series(library_id)

    logger.info(
        "Aggregated %d series for library %s (%d episodes grouped)",
        series_created,
        library_id,
        sum(len(v) for v in groups.values()),
    )
    return series_created


async def _sync_tags_for_series(library_id: int, session=None) -> int:
    """Propagate each series' tag set to all of its episodes.

    Called after scan aggregation to fix "some episodes have tags, others don't":
    for every series with at least one tagged episode, compute the union of all
    tags across its episodes and attach them to every episode (skipping rows
    that already exist). Returns the number of new VideoTag rows created.

    ``session`` is optional — when omitted a fresh ``async_session`` is opened
    (production path) and committed; tests pass their own session (no commit,
    caller controls the transaction).
    """
    synced = 0
    owns_session = session is None
    if owns_session:
        async with async_session() as s:
            return await _sync_tags_for_series_inner(s, library_id, commit=True)
    return await _sync_tags_for_series_inner(session, library_id, commit=False)


async def _sync_tags_for_series_inner(s, library_id: int, *, commit: bool) -> int:
    synced = 0
    result = await s.execute(select(Series.id).where(Series.library_id == library_id))
    series_ids = [row[0] for row in result.all()]
    if not series_ids:
        return 0

    for sid in series_ids:
        # All active episodes of this series
        result = await s.execute(
            select(Media.id).where(
                Media.series_id == sid,
                Media.is_deleted == False,  # noqa: E712
            )
        )
        episode_ids = [row[0] for row in result.all()]
        if len(episode_ids) < 2:
            continue  # single episode: nothing to propagate

        # Union of tags already attached to any episode
        result = await s.execute(
            select(VideoTag.tag_id).where(VideoTag.media_id.in_(episode_ids))
        )
        union_tag_ids = {row[0] for row in result.all()}
        if not union_tag_ids:
            continue  # no tags anywhere yet — nothing to propagate

        # Existing (media, tag) pairs across the series
        result = await s.execute(
            select(VideoTag.media_id, VideoTag.tag_id).where(
                VideoTag.media_id.in_(episode_ids),
                VideoTag.tag_id.in_(union_tag_ids),
            )
        )
        existing_pairs = {(vt.media_id, vt.tag_id) for vt in result.all()}

        created = 0
        for episode_id in episode_ids:
            for tag_id in union_tag_ids:
                if (episode_id, tag_id) not in existing_pairs:
                    s.add(VideoTag(media_id=episode_id, tag_id=tag_id, source="scrape"))
                    created += 1
        if created:
            await s.flush()
            synced += created

    if synced and commit:
        await s.commit()
        logger.info("Synced %d series tag associations for library %s", synced, library_id)
    return synced
