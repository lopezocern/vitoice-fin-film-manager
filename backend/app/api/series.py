"""Series API — list, detail (with episodes), poster, and episode navigation.

Routes:
    GET /series                         — list series (filterable by library, paginated)
    GET /series/{id}                    — series detail with episodes by season
    GET /series/{id}/poster             — serve series poster image
    GET /series/episodes/{media_id}/nav — prev/next episode navigation
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as app_settings
from app.database import get_db
from app.models.media import Media
from app.models.series import Series
from app.services.restricted import get_restricted_library_ids
from app.services.series_view import (
    aggregate_series_response,
    choose_content_owner,
    choose_representative,
    deduplicate_episodes,
    enrich_library_series_response,
    group_equivalent_series,
)
from app.schemas.series import (
    EpisodeNavigation,
    EpisodeResponse,
    PaginatedResponse,
    SeasonGroup,
    SeriesDetailResponse,
    SeriesResponse,
)

router = APIRouter(prefix="/series", tags=["series"])


async def _is_restricted_library(db: AsyncSession, library_id: int | None) -> bool:
    """Return True when the library is hidden by the restricted-content switch."""
    if library_id is None:
        return False
    restricted_ids = await get_restricted_library_ids(db)
    return library_id in restricted_ids


async def _visible_series_groups(
    db: AsyncSession, library_id: int | None = None
) -> tuple[list[list[Series]], dict[int, list[Media]]]:
    """Load visible Series and their active media, grouped for the requested scope."""
    restricted_ids = await get_restricted_library_ids(db)
    filters = [Media.is_deleted == False]  # noqa: E712
    if restricted_ids:
        filters.append(~Media.library_id.in_(restricted_ids))
    if library_id is not None:
        filters.append(Media.library_id == library_id)

    media = list((await db.execute(select(Media).where(*filters, Media.series_id.is_not(None)))).scalars())
    active_series_ids = {item.series_id for item in media if item.series_id is not None}
    if not active_series_ids:
        return [], {}
    series_filters = []
    if library_id is not None:
        series_filters.append(Series.library_id == library_id)
    series_items = list((await db.execute(select(Series).where(*series_filters))).scalars())
    episodes_by_series: dict[int, list[Media]] = {}
    for item in media:
        if item.series_id is not None:
            episodes_by_series.setdefault(item.series_id, []).append(item)

    candidate_groups = (
        [[item] for item in series_items]
        if library_id is not None
        else group_equivalent_series(series_items)
    )
    groups = [
        group
        for group in candidate_groups
        if any(item.id in active_series_ids for item in group)
    ]
    return groups, episodes_by_series


def _episodes_for_group(
    group: list[Series], episodes_by_series: dict[int, list[Media]]
) -> list[Media]:
    return [episode for item in group for episode in episodes_by_series.get(item.id, [])]


def _is_within_poster_root(path: str | None) -> bool:
    """Return True when a path resolves inside the managed poster directory."""
    if not path:
        return False
    try:
        resolved = Path(path).resolve()
        root = app_settings.poster_dir.resolve()
    except (OSError, RuntimeError):
        return False
    return resolved == root or root in resolved.parents


@router.get("", response_model=PaginatedResponse[SeriesResponse])
async def list_series(
    library_id: int | None = Query(None, description="Filter by library"),
    page: int = Query(1, ge=1),
    page_size: int = Query(60, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all series, optionally filtered by library.

    Only includes series with at least one non-deleted episode.
    Paginated to avoid loading large series lists at once.
    """
    groups, episodes_by_series = await _visible_series_groups(db, library_id)
    if library_id is None:
        aggregated = [
            aggregate_series_response(group, _episodes_for_group(group, episodes_by_series))
            for group in groups
        ]
    else:
        global_groups, _ = await _visible_series_groups(db)
        metadata_by_id = {
            item.id: group for group in global_groups for item in group
        }
        aggregated = [
            enrich_library_series_response(
                group[0],
                metadata_by_id.get(group[0].id, group),
                _episodes_for_group(group, episodes_by_series),
            )
            for group in groups
        ]
    aggregated.sort(key=lambda item: (item.title.casefold(), item.year or 0, item.id))
    total = len(aggregated)
    offset = (page - 1) * page_size
    items = aggregated[offset : offset + page_size]

    return PaginatedResponse[SeriesResponse](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{series_id}", response_model=SeriesDetailResponse)
async def get_series(
    series_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get series detail with episodes grouped by season.

    Episodes are ordered by season_number then episode_number.
    Episodes without a season_number are placed in ``unseasoned_episodes``.
    """
    requested = await db.get(Series, series_id)
    if not requested:
        raise HTTPException(status_code=404, detail="Series not found")
    groups, episodes_by_series = await _visible_series_groups(db)
    group = next((items for items in groups if any(item.id == series_id for item in items)), None)
    if not group:
        raise HTTPException(status_code=404, detail="Series not found")
    group_episodes = _episodes_for_group(group, episodes_by_series)
    owner = choose_content_owner(group, group_episodes)
    if await _is_restricted_library(db, owner.library_id):
        raise HTTPException(status_code=404, detail="Series not found")
    metadata = choose_representative(group)
    episodes = deduplicate_episodes(
        group_episodes, owner.library_id
    )

    # Group episodes by season
    season_map: dict[int, list[Media]] = {}
    unseasoned: list[Media] = []
    for ep in episodes:
        if ep.season_number is not None:
            season_map.setdefault(ep.season_number, []).append(ep)
        else:
            unseasoned.append(ep)

    seasons = [
        SeasonGroup(
            season_number=sn,
            episode_count=len(eps),
            episodes=[EpisodeResponse.model_validate(e) for e in eps],
        )
        for sn, eps in sorted(season_map.items())
    ]

    # Build response from series ORM object
    resp = SeriesDetailResponse.model_validate(metadata)
    resp.id = owner.id
    resp.library_id = owner.library_id
    resp.sort_order = owner.sort_order
    resp.created_at = owner.created_at
    resp.updated_at = owner.updated_at
    resp.episode_count = len(episodes)
    resp.seasons = seasons
    resp.unseasoned_episodes = [EpisodeResponse.model_validate(e) for e in unseasoned]
    return resp


@router.get("/{series_id}/poster")
async def get_series_poster(
    series_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Serve the series poster image (falls back to 404 if not scraped)."""
    series = await db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    groups, episodes_by_series = await _visible_series_groups(db)
    group = next((items for items in groups if any(item.id == series_id for item in items)), [series])
    owner = choose_content_owner(group, _episodes_for_group(group, episodes_by_series))
    if await _is_restricted_library(db, owner.library_id):
        raise HTTPException(status_code=404, detail="Series not found")
    series = choose_representative(group)
    if not series.poster_path:
        raise HTTPException(status_code=404, detail="No poster available")

    path = Path(series.poster_path)
    if not _is_within_poster_root(series.poster_path):
        raise HTTPException(status_code=404, detail="Poster file not found on disk")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Poster file not found on disk")

    return FileResponse(str(path), media_type="image/jpeg")


@router.get("/episodes/{media_id}/nav", response_model=EpisodeNavigation)
async def get_episode_navigation(
    media_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get previous/next episode navigation for a media within its series.

    Navigation is based on (season_number, episode_number) ordering.
    Returns has_previous=False, has_next=False if the media has no series.
    """
    media = await db.get(Media, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    if media.is_deleted:
        raise HTTPException(status_code=404, detail="Media not found")
    if await _is_restricted_library(db, media.library_id):
        raise HTTPException(status_code=404, detail="Media not found")

    if not media.series_id:
        return EpisodeNavigation()

    groups, episodes_by_series = await _visible_series_groups(db)
    group = next((items for items in groups if any(item.id == media.series_id for item in items)), None)
    if not group:
        return EpisodeNavigation()
    representative = choose_representative(group)
    episodes = deduplicate_episodes(
        _episodes_for_group(group, episodes_by_series), representative.library_id
    )
    cur_season = media.season_number or 1
    cur_episode = media.episode_number or 0
    previous = [ep for ep in episodes if ((ep.season_number or 1), (ep.episode_number or 0)) < (cur_season, cur_episode)]
    following = [ep for ep in episodes if ((ep.season_number or 1), (ep.episode_number or 0)) > (cur_season, cur_episode)]
    prev_ep = previous[-1] if previous else None
    next_ep = following[0] if following else None

    return EpisodeNavigation(
        has_previous=prev_ep is not None,
        has_next=next_ep is not None,
        previous_id=prev_ep.id if prev_ep else None,
        next_id=next_ep.id if next_ep else None,
        previous_title=prev_ep.title if prev_ep else None,
        next_title=next_ep.title if next_ep else None,
    )
