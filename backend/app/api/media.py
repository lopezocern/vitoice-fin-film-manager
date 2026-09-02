"""Media routes — list, detail, update, delete, stream, thumbnail, progress.

Supports exclude_series filter for unified media view.
"""
from datetime import datetime, timezone
from pathlib import Path
import mimetypes
import os
import asyncio
from collections.abc import AsyncGenerator

# 注册 MKV 等常见但 mimetypes 未内置的容器格式
mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("video/x-matroska", ".mka")

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings as app_settings
from app.database import async_session, get_db
from app.services.proxy import get_proxy_url
from app.services.ssrf import validate_http_url
from app.models.enums import MediaType, UrlRole
from app.models.library import MediaLibrary
from app.models.media import Media, MediaUrl, VideoTag
from app.models.series import Series
from app.models.tag import Tag
from app.services.media_access import get_accessible_media
from app.services.restricted import get_restricted_library_ids
from app.services.series_view import aggregate_series_response, group_equivalent_series
from app.schemas.media import (
    MediaFacetItem,
    MediaFacetsResponse,
    MediaHomeItem,
    MediaHomeResponse,
    MediaListResponse,
    MediaRenameRequest,
    MediaResponse,
    MediaUpdate,
    PlaybackProgressUpdate,
    ProgressResponse,
)
from app.schemas.tag import TagResponse

router = APIRouter(prefix="/media", tags=["media"])

# In-memory lock set to prevent duplicate concurrent scrape requests for the
# same media_id. Cleared in finally block to survive exceptions.
_scraping_media_ids: set[int] = set()

# Asset directories that client-writable poster/thumbnail paths must live in.
# Client-supplied paths outside these roots are rejected to prevent arbitrary
# file read/delete via poster/thumbnail endpoints (S1 security fix).
_ASSET_ROOTS = tuple(
    p.resolve() for p in (app_settings.poster_dir, app_settings.thumbnail_dir)
)


def _resolve_asset_file(db_path: str | None, fallback: Path | None) -> Path | None:
    """Resolve an asset file to serve, with a convention-path fallback.

    Returns an existing Path, or None. Priority:
    1. The DB-stored absolute path — if it is inside an asset root and exists.
    2. The caller-supplied convention fallback (e.g. thumbnail_dir/{id}.jpg) —
       used when the DB path is stale/missing (e.g. after a data-root
       migration); callers may write the resolved path back to the DB.
    """
    if db_path:
        if _is_within_asset_root(db_path):
            p = Path(db_path)
            if p.is_file():
                return p
    if fallback and fallback.is_file() and _is_within_asset_root(str(fallback)):
        return fallback
    return None


def _is_within_asset_root(path: str | None) -> bool:
    """Return True if the path resolves to a location under an asset root.

    Accepts None (no asset) and absolute/relative paths that resolve inside
    poster_dir or thumbnail_dir. Malformed or out-of-root paths return False.
    """
    if not path:
        return True
    try:
        resolved = Path(path).resolve()
    except (OSError, RuntimeError):
        return False
    return any(
        resolved == root or root in resolved.parents for root in _ASSET_ROOTS
    )


# Eager-loading options for a full Media detail row (urls + segments + tags +
# subtitles). Defined once: this exact four-way combination was copy-pasted
# into four call sites, and every new field would otherwise need four edits.
_MEDIA_DETAIL_LOADERS = (
    selectinload(Media.urls),
    selectinload(Media.segments),
    selectinload(Media.video_tags).selectinload(VideoTag.tag),
    selectinload(Media.subtitles),
)


async def _terminate_process(proc: "asyncio.subprocess.Process | None") -> None:
    """Best-effort cleanup of a subprocess, safe to call from `finally`.

    `asyncio.wait_for(proc.communicate(), timeout=N)` cancels the awaiting
    coroutine when the timeout fires but leaves the child process running —
    an orphaned ffprobe keeps pulling the network stream, an orphaned ffmpeg
    keeps burning CPU. Every `wait_for` on a subprocess must be paired with
    this in a `finally` block.

    Mirrors the terminate -> wait -> kill escalation already used in
    `_transcode_stream`.
    """
    if proc is None or proc.returncode is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
    except (asyncio.TimeoutError, ProcessLookupError):
        try:
            proc.kill()
        except ProcessLookupError:
            pass

# Whitelist of columns that can be used for sorting.
# 常见媒体扩展名 → 内容类型。用于 mime_type 缺失时按文件名兜底过滤。
_CONTENT_TYPE_EXTS: dict[str, tuple[str, ...]] = {
    "video": ("mp4", "mkv", "avi", "mov", "wmv", "flv", "ts", "m2ts", "webm", "rmvb", "mpg", "mpeg", "3gp", "m4v", "f4v"),
    "audio": ("mp3", "flac", "wav", "aac", "ogg", "m4a", "wma", "opus", "ape", "alac", "wv"),
    "image": ("jpg", "jpeg", "png", "gif", "webp", "bmp", "tif", "tiff", "heic", "avif", "svg"),
}

# Accepts both frontend-friendly names (filename, size) and model column names
# (file_name, file_size), mapping the former to the latter (H7 fix).
_ALLOWED_SORT_FIELDS: dict[str, str] = {
    "created_at": "created_at",
    "updated_at": "updated_at",
    "title": "title",
    "rating": "rating",
    "duration": "duration",
    "file_size": "file_size",
    "playback_position": "playback_position",
    # Frontend-friendly aliases
    "filename": "file_name",
    "size": "file_size",
}


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so user search text is matched literally."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _content_type_condition(content_type: str):
    """Build the MIME/extension fallback condition shared by lists and facets."""
    ct = content_type.lower()
    cond = Media.mime_type.like(f"{ct}%")
    exts = _CONTENT_TYPE_EXTS.get(ct)
    if not exts:
        return cond
    return or_(
        cond,
        and_(
            Media.mime_type.is_(None),
            or_(*(Media.file_name.ilike(f"%.{ext}") for ext in exts)),
        ),
    )


async def _get_media_or_404(
    db: AsyncSession,
    media_id: int,
    *,
    allow_deleted: bool = False,
) -> Media:
    """Resolve a media row through the shared access gate.

    Thin wrapper kept for the many call sites in this module; the gate itself
    lives in `app.services.media_access` so every other API module can reuse
    it. See that module's docstring for why the bare `db.get(Media, ...)`
    form must not be used in API code.
    """
    return await get_accessible_media(db, media_id, allow_deleted=allow_deleted)


@router.get("", response_model=MediaListResponse)
async def list_media(
    library_id: int | None = Query(None),
    dir: str | None = Query(None, description="Relative directory path to filter by"),
    media_type: MediaType | None = Query(None),
    source: str | None = Query(None, description="Filter by source category: local, network, offline"),
    file_missing: bool | None = Query(None, description="Filter by file_missing status"),
    tag_ids: str | None = Query(None, description="Comma-separated tag IDs"),
    rating_min: int | None = Query(None, ge=1, le=5),
    rating_max: int | None = Query(None, ge=0, le=5, description="Max rating; 0 = unrated (matches NULL rating)"),
    duration_min: float | None = Query(None, description="Min duration in seconds"),
    duration_max: float | None = Query(None, description="Max duration in seconds"),
    resolution_min: int | None = Query(None, description="Min height in pixels"),
    resolution_max: int | None = Query(None, description="Max height in pixels"),
    is_favorite: bool | None = Query(None),
    is_watched: bool | None = Query(None),
    in_progress: bool | None = Query(None, description="Filter media with playback progress > 0 and not watched"),
    search: str | None = Query(None),
    exclude_series: bool | None = Query(None, description="Exclude media that belongs to a series (TV episodes aggregated as Series)"),
    has_series: bool | None = Query(None, description="Filter by whether media belongs to a TV series"),
    year: int | None = Query(None, description="Filter by release year"),
    genre: str | None = Query(None, description="Filter by genre (from scrape_data.genres)"),
    country: str | None = Query(None, description="Filter by production country (from scrape_data.production_countries)"),
    content_type: str | None = Query(None, description="Filter by content type: video, audio, image (matches mime_type prefix)"),
    tag_match: str = Query("any", pattern="^(any|all)$", description="Match any or all tag_ids"),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List media with filtering, sorting, and pagination.

    Supports filtering by library, type, tags, rating, duration, resolution,
    and text search across title/file_name.

    When ``exclude_series=True`` only standalone media (movies etc.) are
    returned — TV episodes that belong to a Series are excluded so the
    caller can fetch Series separately via /series.
    """
    query = select(Media).where(Media.is_deleted == False)  # noqa: E712

    # --- Content restriction filter ---
    restricted_ids = await get_restricted_library_ids(db)
    if restricted_ids:
        query = query.where(~Media.library_id.in_(restricted_ids))

    # --- Filters ---
    if library_id is not None:
        query = query.where(Media.library_id == library_id)
    if dir and library_id is not None:
        # Build the absolute directory prefix from library root + relative dir
        # Normalize separators: dir may contain forward or backslashes
        dir_clean = dir.strip().strip("/\\")
        if dir_clean:
            lib = await db.get(MediaLibrary, library_id)
            if lib and lib.root_path:
                dir_prefix = str(Path(lib.root_path) / dir_clean).rstrip("/\\")
                # Compare separator- and case-normalized (Windows paths are
                # case-insensitive; DB values may mix separators)
                norm_prefix = dir_prefix.replace("\\", "/").lower() + "/"
                query = query.where(
                    func.replace(func.lower(Media.file_path), "\\", "/").startswith(
                        norm_prefix
                    )
                )
    if exclude_series is True:
        query = query.where(Media.series_id.is_(None))
    if has_series is True:
        query = query.where(Media.series_id.is_not(None))
    elif has_series is False:
        query = query.where(Media.series_id.is_(None))
    if media_type is not None:
        query = query.where(Media.media_type == media_type)
    if source:
        source_lower = source.lower()
        if source_lower == "local":
            # Media with playable local files (LOCAL or BOTH, not missing)
            query = query.where(
                Media.media_type.in_([MediaType.LOCAL, MediaType.BOTH]),
                Media.file_missing == False,  # noqa: E712
            )
        elif source_lower == "network":
            # Media with network sources (NETWORK or BOTH)
            query = query.where(
                Media.media_type.in_([MediaType.NETWORK, MediaType.BOTH])
            )
        elif source_lower in ("offline", "missing"):
            # Media whose local file is missing
            query = query.where(Media.file_missing == True)  # noqa: E712
    if file_missing is not None:
        query = query.where(Media.file_missing == file_missing)
    if content_type:
        # 按 mime_type 前缀过滤 (video%/audio%/image%)。
        # 大量旧媒体 mime_type 为 NULL（入库时未做探测），此时退回按文件扩展名
        # 兜底判断，否则"类型筛选"会把所有这类媒体过滤成 0 项。
        query = query.where(_content_type_condition(content_type))
    if rating_min is not None:
        query = query.where(Media.rating >= rating_min)
    if rating_max is not None:
        if rating_max <= 0:
            # 未评分: 无评分记录(rating 为 NULL,大部分未评媒体)或评分为 0。
            # 注意 rating <= 0 匹配不到 NULL,必须显式 OR 上 IS NULL。
            query = query.where(or_(Media.rating.is_(None), Media.rating <= 0))
        else:
            query = query.where(Media.rating <= rating_max)
    if duration_min is not None:
        query = query.where(Media.duration >= duration_min)
    if duration_max is not None:
        query = query.where(Media.duration <= duration_max)
    if resolution_min is not None:
        query = query.where(Media.height >= resolution_min)
    if resolution_max is not None:
        query = query.where(Media.height <= resolution_max)
    if is_favorite is not None:
        query = query.where(Media.is_favorite == is_favorite)
    if is_watched is not None:
        query = query.where(Media.is_watched == is_watched)
    if in_progress is True:
        query = query.where(
            Media.playback_position > 0,
            Media.is_watched == False,  # noqa: E712
        )
    if search:
        pattern = f"%{_escape_like(search)}%"
        query = query.where(
            or_(
                Media.title.ilike(pattern, escape="\\"),
                Media.file_name.ilike(pattern, escape="\\"),
            )
        )

    # Tag filtering — media must have at least one of the specified tags
    if tag_ids:
        try:
            parsed_ids = list({int(t.strip()) for t in tag_ids.split(",") if t.strip()})
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="tag_ids must contain integers") from exc
        if parsed_ids:
            if tag_match == "all":
                matching_media = (
                    select(VideoTag.media_id)
                    .where(VideoTag.tag_id.in_(parsed_ids))
                    .group_by(VideoTag.media_id)
                    .having(func.count(func.distinct(VideoTag.tag_id)) == len(parsed_ids))
                )
            else:
                matching_media = select(VideoTag.media_id).where(VideoTag.tag_id.in_(parsed_ids))
            query = query.where(Media.id.in_(matching_media))

    # Year filter (column on Media table)
    # year=0 表示"未知年份"（Media.year 为 NULL 的记录）——前端年份下拉的"未知年份"选项
    if year is not None:
        if year == 0:
            query = query.where(Media.year.is_(None))
        else:
            query = query.where(Media.year == year)

    # Genre filter (JSON array in scrape_data.genres — SQLite json_extract)
    if genre:
        query = query.where(
            text("json_extract(scrape_data, '$.genres') LIKE :genre_pattern").bindparams(
                genre_pattern=f'%"{genre}"%'
            )
        )

    # Country filter (JSON array in scrape_data.production_countries)
    if country:
        query = query.where(
            text("json_extract(scrape_data, '$.production_countries') LIKE :country_pattern").bindparams(
                country_pattern=f'%"{country}"%'
            )
        )

    # --- Total count ---
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # --- Sorting ---
    safe_sort_by = _ALLOWED_SORT_FIELDS.get(sort_by, "created_at")
    sort_column = getattr(Media, safe_sort_by, None)
    if sort_column is None:
        sort_column = Media.created_at
    if sort_order.lower() == "asc":
        query = query.order_by(sort_column.asc())
    else:
        query = query.order_by(sort_column.desc())

    # --- Pagination ---
    offset = (page - 1) * page_size
    # Eager-load tags for list view (selectinload avoids N+1 queries)
    query = query.options(
        selectinload(Media.video_tags).selectinload(VideoTag.tag),
    ).offset(offset).limit(page_size)

    result = await db.execute(query)
    media_list = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    # Build response items with tags mapped from video_tags
    response_items: list[MediaResponse] = []
    for m in media_list:
        resp = MediaResponse.model_validate(m)
        resp.tags = [TagResponse.model_validate(vt.tag) for vt in m.video_tags]
        response_items.append(resp)

    # 缩略图集存在性 — 一次目录扫描填充（避免每卡片一次 stat 的 N+1）
    if response_items:
        from app.services.contact_sheet import contact_sheet_path

        cs_dir = contact_sheet_path(0).parent
        try:
            existing_cs = {
                int(f.stem)
                for f in cs_dir.glob("*.jpg")
                if f.stem.isdigit()
            }
        except OSError:
            existing_cs = set()
        for resp in response_items:
            resp.has_contact_sheet = resp.id in existing_cs

    return MediaListResponse(
        items=response_items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/facets", response_model=MediaFacetsResponse)
async def get_media_facets(
    library_id: int | None = Query(None, description="Scope counts & tags to a single library"),
    db: AsyncSession = Depends(get_db),
):
    """Return consistent counts and compact filter options for visible media.

    ``library_id`` scopes the results to one library so the media page's分类
    buttons and tag filter row refresh when switching libraries; omitted means
    the whole (restricted-filtered) library set.
    """
    visible = [Media.is_deleted == False]  # noqa: E712
    if library_id is not None:
        visible.append(Media.library_id == library_id)
    else:
        restricted_ids = await get_restricted_library_ids(db)
        if restricted_ids:
            visible.append(~Media.library_id.in_(restricted_ids))

    async def count_media(*conditions) -> int:
        result = await db.execute(select(func.count(Media.id)).where(*visible, *conditions))
        return int(result.scalar() or 0)

    active_series_result = await db.execute(
        select(Series)
        .join(Media, Media.series_id == Series.id)
        .where(*visible)
        .distinct()
    )
    series_count = len(group_equivalent_series(active_series_result.scalars().all()))

    rows_result = await db.execute(select(Media.scrape_data, Media.year).where(*visible))
    genre_counts: dict[str, int] = {}
    country_counts: dict[str, int] = {}
    year_counts: dict[str, int] = {}
    for scrape_data, year in rows_result.all():
        if year:
            year_counts[str(year)] = year_counts.get(str(year), 0) + 1
        if not isinstance(scrape_data, dict):
            continue
        for genre in scrape_data.get("genres", []) or []:
            if isinstance(genre, str) and genre.strip():
                key = genre.strip()
                genre_counts[key] = genre_counts.get(key, 0) + 1
        for country in scrape_data.get("production_countries", []) or []:
            if isinstance(country, str) and country.strip():
                key = country.strip()
                country_counts[key] = country_counts.get(key, 0) + 1

    tag_query = (
        select(Tag.id, Tag.name, Tag.color, func.count(func.distinct(Media.id)))
        .join(VideoTag, VideoTag.tag_id == Tag.id)
        .join(Media, Media.id == VideoTag.media_id)
        .where(*visible)
        .group_by(Tag.id, Tag.name, Tag.color)
        .order_by(func.count(func.distinct(Media.id)).desc(), Tag.name)
        .limit(24)
    )
    tag_rows = (await db.execute(tag_query)).all()
    video = _content_type_condition("video")

    return MediaFacetsResponse(
        # Home-page entities: standalone media plus each TV Series once.
        # Episodes are represented by their Series and must not be double-counted.
        all=await count_media(Media.series_id.is_(None)) + series_count,
        movies=await count_media(video, Media.series_id.is_(None)),
        series=series_count,
        episodes=await count_media(Media.series_id.is_not(None)),
        images=await count_media(_content_type_condition("image")),
        audio=await count_media(_content_type_condition("audio")),
        genres=[MediaFacetItem(value=k, count=v) for k, v in sorted(genre_counts.items())],
        countries=[MediaFacetItem(value=k, count=v) for k, v in sorted(country_counts.items())],
        years=[MediaFacetItem(value=k, count=v) for k, v in sorted(year_counts.items(), reverse=True)],
        tags=[
            {"id": row[0], "value": row[1], "color": row[2], "count": row[3]}
            for row in tag_rows
        ],
    )


async def _home_media_item(media: Media) -> MediaHomeItem:
    response = MediaResponse.model_validate(media)
    response.tags = [TagResponse.model_validate(vt.tag) for vt in media.video_tags]
    return MediaHomeItem(kind="media", data=response)


@router.get("/home", response_model=MediaHomeResponse)
async def get_media_home(
    recommendation_seed: int | None = Query(None, description="Changes the recommendation batch"),
    db: AsyncSession = Depends(get_db),
):
    """Return watch-center shelves, following the content-restriction switch.

    Uses get_restricted_library_ids() so restricted libraries (e.g. AZV) are
    hidden only when the user disabled \"show restricted\" — mirroring the media
    list endpoints instead of always hiding restricted content.
    """
    restricted_ids = await get_restricted_library_ids(db)
    visible = [Media.is_deleted == False]  # noqa: E712
    if restricted_ids:
        visible.append(~Media.library_id.in_(restricted_ids))

    media_options = (selectinload(Media.video_tags).selectinload(VideoTag.tag),)
    continue_query = (
        select(Media)
        .where(
            *visible,
            Media.playback_position > 0,
            Media.is_watched == False,  # noqa: E712
            Media.last_played_at.is_not(None),
        )
        .options(*media_options)
        .order_by(Media.last_played_at.desc())
        .limit(6)
    )
    played_query = (
        select(Media)
        .where(*visible, Media.last_played_at.is_not(None))
        .options(*media_options)
        .order_by(Media.last_played_at.desc())
        .limit(6)
    )
    added_query = (
        select(Media)
        .where(*visible, Media.series_id.is_(None))
        .options(*media_options)
        .order_by(Media.created_at.desc())
        .limit(6)
    )

    continue_media = (await db.execute(continue_query)).scalars().all()
    played_media = (await db.execute(played_query)).scalars().all()
    added_media = (await db.execute(added_query)).scalars().all()

    # Recommendations are deliberately limited to movies and aggregated TV
    # series. A changing seed keeps SQLite's random selection easy to refresh.
    video = _content_type_condition("video")
    recommendation_query = (
        select(Media)
        .where(*visible, Media.series_id.is_(None), video)
        .options(*media_options)
        .order_by(func.random() + (recommendation_seed or 0))
        .limit(6)
    )
    recommended_media = (await db.execute(recommendation_query)).scalars().all()

    series_conditions = [Media.is_deleted == False]  # noqa: E712
    if restricted_ids:
        series_conditions.append(~Media.library_id.in_(restricted_ids))
    series_query = (
        select(Series)
        .join(Media, Media.series_id == Series.id)
        .where(*series_conditions)
        .distinct()
        .order_by(func.random() + (recommendation_seed or 0))
        .limit(3)
    )
    active_recommended_series = (await db.execute(series_query)).scalars().all()
    active_recommended_ids = {item.id for item in active_recommended_series}
    all_series = (await db.execute(select(Series))).scalars().all()
    recommendation_groups = [
        group
        for group in group_equivalent_series(all_series)
        if any(item.id in active_recommended_ids for item in group)
    ][:3]

    recommendations: list[MediaHomeItem] = []
    for group in recommendation_groups:
        group_episodes = (
            await db.execute(
                select(Media).where(
                    Media.series_id.in_([item.id for item in group]),
                    Media.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars().all()
        recommendations.append(
            MediaHomeItem(
                kind="series",
                data=aggregate_series_response(group, group_episodes),
            )
        )
    movie_slots = max(0, 6 - len(recommendations))
    recommendations = [
        *[await _home_media_item(m) for m in recommended_media[:movie_slots]],
        *recommendations,
    ]

    return MediaHomeResponse(
        continue_watching=[await _home_media_item(m) for m in continue_media],
        recently_added=[await _home_media_item(m) for m in added_media],
        recently_played=[await _home_media_item(m) for m in played_media],
        recommendations=recommendations[:6],
    )


@router.get("/filters")
async def get_filter_options(db: AsyncSession = Depends(get_db)):
    """Return available filter options (genres, countries, years) from scraped media.

    Scans non-deleted media with scrape_data and extracts unique values for
    genres, production_countries, and years. Used by the frontend to populate
    filter dropdowns.

    Respects the content restriction setting — media from restricted libraries
    are excluded from filter options.
    """
    query = select(Media.scrape_data, Media.year).where(Media.is_deleted == False)  # noqa: E712

    # --- Content restriction filter ---
    restricted_ids = await get_restricted_library_ids(db)
    if restricted_ids:
        query = query.where(~Media.library_id.in_(restricted_ids))

    result = await db.execute(query)
    rows = result.all()

    genres: set[str] = set()
    countries: set[str] = set()
    years: set[int] = set()

    for scrape_data, yr in rows:
        if yr:
            years.add(yr)
        if scrape_data and isinstance(scrape_data, dict):
            for g in scrape_data.get("genres", []) or []:
                if isinstance(g, str) and g.strip():
                    genres.add(g.strip())
            for c in scrape_data.get("production_countries", []) or []:
                if isinstance(c, str) and c.strip():
                    countries.add(c.strip())

    return {
        "genres": sorted(genres),
        "countries": sorted(countries),
        "years": sorted(years, reverse=True),
    }


# ---------------------------------------------------------------------------
# Missing-file reconciliation (shadow-duplicate merge)
# NOTE: must be declared BEFORE /{media_id} routes — "missing" would otherwise
# be captured by the int path param.
# ---------------------------------------------------------------------------


@router.get("/missing/reconcile-preview")
async def missing_reconcile_preview(
    library_id: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Preview file_missing records that have a live same-name twin to merge into."""
    from app.services.missing_reconcile import find_pairs

    pairs = await find_pairs(db, [library_id] if library_id else None)
    return {"pairs": pairs, "count": len(pairs)}


@router.post("/missing/reconcile")
async def missing_reconcile_execute(
    payload: dict, db: AsyncSession = Depends(get_db)
):
    """Execute reconciliation for the given pairs.

    Body: ``{"pairs": [{"missing_id": int, "live_id": int}, ...]}``.
    Each pair is re-validated at execute time — stale pairs fail individually
    without blocking the rest.
    """
    from app.services.missing_reconcile import reconcile_pairs

    pairs = payload.get("pairs") or []
    if not pairs:
        raise HTTPException(status_code=400, detail="pairs is required")
    result = await reconcile_pairs(db, pairs)
    return result


@router.get("/{media_id}", response_model=MediaResponse)
async def get_media(media_id: int, db: AsyncSession = Depends(get_db)):
    """Get media detail with urls, segments, tags, and subtitles."""
    query = (
        select(Media)
        .where(Media.id == media_id)
        .options(
            *_MEDIA_DETAIL_LOADERS,
        )
    )
    result = await db.execute(query)
    media = result.scalar_one_or_none()
    if not media or media.is_deleted:
        raise HTTPException(status_code=404, detail="Media not found")
    # S7: single-resource access must respect the restricted-content switch
    # (same semantics as _get_media_or_404; no-op when show_restricted is on).
    restricted_ids = await get_restricted_library_ids(db)
    if restricted_ids and media.library_id in restricted_ids:
        raise HTTPException(status_code=404, detail="Media not found")

    resp = MediaResponse.model_validate(media)
    # Map video_tags -> tags (Media model uses video_tags, API exposes tags)
    resp.tags = [TagResponse.model_validate(vt.tag) for vt in media.video_tags]
    return resp


@router.put("/{media_id}", response_model=MediaResponse)
async def update_media(
    media_id: int,
    payload: MediaUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update media metadata (rating, favorite, description, etc.)."""
    media = await _get_media_or_404(db, media_id)

    # Validate target library exists when library_id is provided (C3 fix)
    if payload.library_id is not None and payload.library_id != media.library_id:
        target = await db.get(MediaLibrary, payload.library_id)
        if not target:
            raise HTTPException(status_code=400, detail="目标资源库不存在")
        # uq_media_library_file: target library must not already hold a row
        # (incl. soft-deleted) with the same file_path.
        if media.file_path:
            dup = await db.execute(
                select(Media.id).where(
                    Media.library_id == payload.library_id,
                    Media.file_path == media.file_path,
                    Media.id != media.id,
                )
            )
            if dup.scalar_one_or_none():
                raise HTTPException(
                    status_code=409,
                    detail="目标资源库已存在相同文件路径的记录",
                )

    update_data = payload.model_dump(exclude_unset=True)

    # S1 security fix: client-supplied asset paths must stay inside the
    # managed poster/thumbnail directories. Reject anything outside them so
    # poster/thumbnail endpoints cannot be abused for arbitrary file access.
    for field in ("poster_path", "thumbnail_path"):
        if field in update_data and not _is_within_asset_root(update_data[field]):
            raise HTTPException(
                status_code=400,
                detail=f"{field} 必须在应用的封面/缩略图目录内",
            )

    for field, value in update_data.items():
        setattr(media, field, value)
    await db.flush()
    await db.refresh(media)
    return MediaResponse.model_validate(media)


# Windows and Unix illegal filename characters
_ILLEGAL_CHARS = set('<>:"/\\|?*')


def _validate_filename(name: str) -> str:
    """Validate a filename — must not contain path separators or illegal chars."""
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="文件名不能为空")
    name = name.strip()
    # Block path traversal — reject any path separator or parent reference
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="文件名不能包含路径分隔符")
    # Check for illegal characters
    bad = set(name) & _ILLEGAL_CHARS
    if bad:
        raise HTTPException(
            status_code=400,
            detail=f"文件名包含非法字符: {' '.join(sorted(bad))}",
        )
    return name


@router.put("/{media_id}/rename", response_model=MediaResponse)
async def rename_media_file(
    media_id: int,
    payload: MediaRenameRequest,
    db: AsyncSession = Depends(get_db),
):
    """Rename the physical file on disk and update the Media record.

    Only the filename portion is changed — the file stays in its current
    directory. After renaming, optionally triggers re-scraping (useful
    when the user renames to fix a parsing issue).

    Security:
    - The new name is validated (no path traversal, no illegal chars)
    - The resulting path must stay within the library root_path
    - The destination must not already exist
    """
    media = await _get_media_or_404(db, media_id)

    if not media.file_path:
        raise HTTPException(
            status_code=400,
            detail="该媒体没有本地文件路径（网络媒体无法重命名）",
        )

    if media.file_missing:
        raise HTTPException(
            status_code=410,
            detail="本地文件已丢失，无法重命名",
        )

    old_path = Path(media.file_path)
    if not old_path.is_file():
        raise HTTPException(
            status_code=410,
            detail="原始文件在磁盘上未找到",
        )

    new_name = _validate_filename(payload.new_name)

    # Preserve the extension if the user didn't include it
    old_ext = old_path.suffix
    new_ext = Path(new_name).suffix
    if not new_ext and old_ext:
        new_name = new_name + old_ext

    new_path = old_path.parent / new_name

    # Check destination doesn't exist (unless it's the same file)
    if new_path != old_path and new_path.exists():
        raise HTTPException(
            status_code=409,
            detail=f"目标文件已存在: {new_name}",
        )

    # uq_media_library_file: a soft-deleted row may occupy the target path
    # even though the file is gone from disk.
    if new_path != old_path:
        dup = await db.execute(
            select(Media.id).where(
                Media.library_id == media.library_id,
                Media.file_path == str(new_path),
                Media.id != media.id,
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail=f"目标路径已被其他记录占用: {new_name}",
            )

    # Verify the new path is still within the library root
    from app.models.library import MediaLibrary
    lib = await db.get(MediaLibrary, media.library_id)
    if lib:
        try:
            from app.services.scanner import validate_root_path
            root = validate_root_path(lib.root_path)
            new_path.resolve().relative_to(root)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="重命名后的路径超出了库的范围",
            )
        except (OSError, RuntimeError):
            # Filename was already sanitized above, so the path stays in the
            # same directory; only tolerate filesystem-level resolution errors.
            pass

    # Rename the physical file
    try:
        old_path.rename(new_path)
    except OSError as exc:
        # Fallback: shutil.move handles cross-device and locked-file cases better
        try:
            import shutil
            shutil.move(str(old_path), str(new_path))
        except (OSError, shutil.Error) as exc2:
            raise HTTPException(
                status_code=500,
                detail=f"文件重命名失败: {exc2}",
            )

    # Update the Media record
    media.file_path = str(new_path)
    media.file_name = new_name
    # Reset scrape data so re-scraping starts fresh
    if payload.re_scrape:
        media.scrape_data = None
        media.poster_path = None
        media.year = None
        media.release_date = None
        media.season_number = None
        media.episode_number = None
        media.series_id = None
        media.series_title = None
    await db.flush()
    await db.commit()

    # Optionally trigger re-scraping
    if payload.re_scrape:
        from app.services.scraper import scrape_media, TMDBConfigError
        import httpx
        try:
            result = await scrape_media(media_id)
            if result.matched:
                await db.commit()
        except TMDBConfigError:
            pass  # TMDB not configured — file was still renamed
        except httpx.HTTPError:
            pass  # Network error — file was still renamed
        except Exception:
            pass  # Any scrape failure — file rename still succeeded

    # Return the refreshed media record
    query = (
        select(Media)
        .where(Media.id == media_id)
        .options(
            *_MEDIA_DETAIL_LOADERS,
        )
    )
    result_q = await db.execute(query)
    media = result_q.scalar_one_or_none()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found after rename")
    resp = MediaResponse.model_validate(media)
    resp.tags = [TagResponse.model_validate(vt.tag) for vt in media.video_tags]
    return resp


@router.delete("/{media_id}", status_code=204)
async def delete_media(media_id: int, db: AsyncSession = Depends(get_db)):
    """Soft-delete a media record (move to recycle bin).

    Marks ``is_deleted=True`` and ``deleted_at=now()``. The physical file
    is preserved. Use ``DELETE /api/recycle-bin/{id}/permanent`` for
    irreversible deletion.
    """
    media = await _get_media_or_404(db, media_id)
    media.is_deleted = True
    media.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()


@router.post("/{media_id}/convert-to-network", response_model=MediaResponse)
async def convert_to_network(media_id: int, db: AsyncSession = Depends(get_db)):
    """Convert a file-missing (OFFLINE) media into a pure network video (NETWORK).

    Use case: the local file was lost (file_missing=True, media_type=OFFLINE)
    but a playable network source exists (or the user just added one via the
    aggregator resolve / manual link). This endpoint makes the media a first-class
    network video:

      - media_type: OFFLINE → NETWORK
      - file_missing: True → False
      - missing_detected_at: None
      - file_path: None  (NETWORK canonical shape; also prevents the scanner from
                          re-marking the record as missing on the next pass)

    Preconditions:
      - the media must be file_missing with media_type OFFLINE (400 otherwise)
      - at least one non-expired SOURCE URL must exist (422 otherwise — the
        caller should add a source first via aggregator resolve or manual link)
    """
    media = await _get_media_or_404(db, media_id)

    if not media.file_missing:
        raise HTTPException(status_code=400, detail="该媒体本地文件未丢失，无需转为网络视频")
    if media.media_type not in (MediaType.OFFLINE, MediaType.BOTH):
        raise HTTPException(
            status_code=400,
            detail=f"仅支持将 OFFLINE/BOTH（文件丢失）媒体转为网络视频（当前类型：{media.media_type}）",
        )

    # Must have a playable source — otherwise converting leaves nothing to play.
    net_result = await db.execute(
        select(MediaUrl.media_id)
        .where(
            MediaUrl.media_id == media_id,
            MediaUrl.url_role == UrlRole.SOURCE,
            MediaUrl.is_expired == False,  # noqa: E712
        )
        .limit(1)
    )
    if net_result.fetchone() is None:
        raise HTTPException(
            status_code=422,
            detail="该媒体没有可播放的网络源，请先通过「从聚合站解析」或手动添加源链接",
        )

    # Full conversion to a canonical NETWORK record.
    media.media_type = MediaType.NETWORK
    media.file_missing = False
    media.missing_detected_at = None
    media.file_path = None
    await db.flush()

    # Reload with relations for the full MediaResponse.
    result = await db.execute(
        select(Media)
        .where(Media.id == media_id)
        .options(
            *_MEDIA_DETAIL_LOADERS,
        )
    )
    media = result.scalar_one()
    return MediaResponse.model_validate(media)


# ---------------------------------------------------------------------------
# Media URL CRUD and AI tagging endpoints have been extracted to:
#   - media_urls.py  (POST/PUT/DELETE /media/{id}/urls)
#   - media_ai.py    (POST /media/{id}/ai-tags)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# FFmpeg-based transcoding for browser-incompatible codecs
# ---------------------------------------------------------------------------

# 浏览器兼容的视频/音频编码
_BROWSER_VIDEO_CODECS = {"h264", "vp8", "vp9", "av1", "avc", "avc1"}
_BROWSER_AUDIO_CODECS = {"aac", "mp3", "opus", "vorbis", "flac"}


# Cache the found paths — delegate to the unified ffmpeg_utils module
from app.services.ffmpeg_utils import get_ffmpeg as _get_ffmpeg, get_ffprobe as _get_ffprobe
from app.services.thumbnail import generate_thumbnail as _generate_thumbnail
from app.config import settings as _settings


async def _probe_codecs(path: Path) -> tuple[str | None, str | None]:
    """Use ffprobe to detect video and audio codec names.

    ffprobe with ``-of csv=p=0`` outputs fields in alphabetical order,
    so each line is ``codec_name,codec_type`` (e.g. ``h264,video``).
    """
    try:
        ffprobe = _get_ffprobe()
        proc = await asyncio.create_subprocess_exec(
            ffprobe, "-v", "error",
            "-show_entries", "stream=codec_type,codec_name",
            "-of", "csv=p=0",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        video_codec: str | None = None
        audio_codec: str | None = None
        for line in stdout.decode().strip().split("\n"):
            parts = line.strip().split(",")
            if len(parts) >= 2:
                # ffprobe csv output is alphabetically ordered:
                # codec_name comes before codec_type
                codec, stream_type = parts[0].strip(), parts[1].strip()
                if stream_type == "video" and not video_codec:
                    video_codec = codec.lower()
                elif stream_type == "audio" and not audio_codec:
                    audio_codec = codec.lower()
        return video_codec, audio_codec
    except Exception:
        return None, None


def _needs_transcoding(
    path: Path,
    video_codec: str | None,
    audio_codec: str | None,
) -> bool:
    """Check if the file needs FFmpeg transcoding for browser playback.

    MKV containers are always remuxed/transcoded because browser MKV
    support is unreliable. Files with incompatible audio (AC3, DTS, EAC3)
    or video (HEVC/H.265) codecs are also transcoded.
    """
    ext = path.suffix.lower()

    # MKV 容器：浏览器支持不稳定，始终转封装/转码
    if ext == ".mkv":
        return True

    # 检查视频编码
    if video_codec and video_codec not in _BROWSER_VIDEO_CODECS:
        return True

    # 检查音频编码
    if audio_codec and audio_codec not in _BROWSER_AUDIO_CODECS:
        return True

    return False


async def _transcode_stream(
    path: Path,
    video_codec: str | None,
    start_time: float = 0,
) -> AsyncGenerator[bytes, None]:
    """Transcode media to browser-compatible fragmented MP4 via FFmpeg.

    - H.264 video is copied (fast); other codecs are transcoded to H.264
    - Audio is always transcoded to AAC (browser-safe)
    - Output is fragmented MP4 for progressive streaming

    Must be an **async** generator. As a sync generator Starlette served it via
    `iterate_in_threadpool`, so every concurrent playback parked a worker
    thread for the whole request; AnyIO's default limit is 40 threads, and
    exhausting them stalled unrelated `asyncio.to_thread` work (thumbnails,
    subtitle extraction, backups).
    """
    cmd: list[str] = [_get_ffmpeg(), "-nostdin"]

    # 快速 seek（input 之前），速度快但位置可能不够精确
    if start_time > 0:
        cmd.extend(["-ss", f"{start_time:.3f}"])

    cmd.extend(["-i", str(path)])

    # 视频：H.264 直接复制，其他转码
    if video_codec in ("h264", "avc", "avc1"):
        cmd.extend(["-c:v", "copy"])
    else:
        cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23"])

    # 音频：始终转码为 AAC（浏览器全兼容）
    cmd.extend(["-c:a", "aac", "-b:a", "192k", "-ac", "2"])

    # 分片 MP4，支持渐进式播放
    cmd.extend([
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "-f", "mp4",
        "pipe:1",
    ])

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        assert proc.stdout is not None
        while True:
            # Awaiting on the pipe yields to the event loop instead of
            # occupying a worker thread for the duration of the stream.
            chunk = await proc.stdout.read(1024 * 1024)
            if not chunk:
                break
            yield chunk
    finally:
        await _terminate_process(proc)


@router.get("/{media_id}/stream")
async def stream_media(
    media_id: int,
    request: Request,
    start: float = Query(0, ge=0, description="Start time in seconds (for transcoded streams)"),
):
    """Stream the media file with HTTP Range support for video seeking.

    For browser-incompatible files (MKV container, AC3/DTS audio, HEVC video),
    FFmpeg transcodes to fragmented MP4 with H.264 video + AAC audio in real-time.
    For compatible files, direct Range-based streaming is used.

    Note: DB connection is released right after fetching the file info — the
    stream itself can last minutes and must not hold the (single) SQLite
    connection, or every other request would time out waiting for the pool.
    """
    # Pre-fetch file info inside a short-lived session, then release the
    # connection before streaming (see note above).
    async with async_session() as db:
        media = await _get_media_or_404(db, media_id)
        if not media.file_path:
            raise HTTPException(
                status_code=400,
                detail="Media has no local file path (network-only media)",
            )
        if media.file_missing:
            raise HTTPException(
                status_code=410,
                detail="本地文件已丢失，请从网络源播放或恢复文件",
            )
        path = Path(media.file_path)
        if not path.is_file():
            raise HTTPException(status_code=410, detail="Media file not found on disk")
        mime_type = media.mime_type
    # ---- connection released from here on ----

    # 探测编码格式
    video_codec, audio_codec = await _probe_codecs(path)
    needs_ts = _needs_transcoding(path, video_codec, audio_codec)

    # 需要转码：使用 FFmpeg 实时转码为浏览器兼容的 MP4
    if needs_ts:
        return StreamingResponse(
            _transcode_stream(path, video_codec, start),
            media_type="video/mp4",
            status_code=200,
            headers={
                "Accept-Ranges": "none",
                "Cache-Control": "no-cache",
                "X-Transcoded": "1",
            },
        )

    # 直接播放（浏览器兼容的编码格式）
    file_size = path.stat().st_size
    # 推断 MIME 类型：优先使用数据库记录，其次按文件扩展名推断
    if mime_type:
        media_type = mime_type
    else:
        guessed, _ = mimetypes.guess_type(str(path))
        media_type = guessed or "video/mp4"

    # --- Parse Range header for partial content (video seeking) ---
    range_header = request.headers.get("range")
    if range_header:
        try:
            range_spec = range_header.strip().lower()
            if not range_spec.startswith("bytes="):
                raise ValueError("Unsupported range unit")
            range_part = range_spec[6:]
            # Use only the first range if multiple are requested
            range_part = range_part.split(",")[0].strip()
            start_str, _, end_str = range_part.partition("-")

            if start_str and end_str:
                start = int(start_str)
                end = int(end_str)
            elif start_str:  # "bytes=1000-"
                start = int(start_str)
                end = file_size - 1
            elif end_str:  # "bytes=-500" → last 500 bytes
                suffix_len = int(end_str)
                start = max(0, file_size - suffix_len)
                end = file_size - 1
            else:
                raise ValueError("Invalid range format")

            # Clamp to valid bounds
            start = max(0, min(start, file_size - 1))
            end = max(start, min(end, file_size - 1))
        except (ValueError, IndexError):
            raise HTTPException(
                status_code=416,
                detail="Invalid Range header",
                headers={"Content-Range": f"bytes */{file_size}"},
            )

        content_length = end - start + 1

        def _iter_range(start: int, length: int) -> bytes:
            """Yield file chunks synchronously (1 MB per chunk)."""
            with open(str(path), "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            _iter_range(start, content_length),
            media_type=media_type,
            status_code=206,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(content_length),
                "Accept-Ranges": "bytes",
            },
        )

    # No Range header — return full file
    # 必须显式声明 Accept-Ranges: bytes：浏览器 video 首次请求不带 Range，
    # 若响应无此头会被视为"不可 seek 的渐进式流"——duration 只显示已缓冲部分、
    # 拖动进度条被拒绝 → 进度条跳回开头（实测 media 15 MP4 复现）。
    return FileResponse(
        str(path),
        media_type=media_type,
        filename=media.file_name,
        headers={"Accept-Ranges": "bytes"},
    )


def _is_hls(content_type: str, url: str) -> bool:
    """True when a response looks like an HLS playlist (content-type or URL)."""
    ct = (content_type or "").lower()
    path = url.lower().split("?")[0]
    return "mpegurl" in ct or path.endswith(".m3u8")


def _rewrite_m3u8(text: str, media_id: int, url_id: int | None, base: str) -> str:
    """Rewrite every external resource in an HLS manifest to go through the
    backend proxy, so fragments / nested playlists no longer hit the CDN
    directly (which broke on CORS / Referer)."""
    import re
    import urllib.parse

    def wrap(ref: str) -> str:
        abs_url = urllib.parse.urljoin(base, ref)
        return f"/media/{media_id}/network-part?fetch={urllib.parse.quote(abs_url, safe='')}"

    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#EXT-X-KEY"):
            if s.startswith("#EXT-X-KEY"):
                line = re.sub(
                    r'URI="([^"]+)"',
                    lambda m: f'URI="{wrap(m.group(1))}"',
                    line,
                )
            out.append(line)
            continue
        if s.startswith("#"):
            out.append(line)
            continue
        # A bare URL row: media segment or nested playlist.
        out.append(wrap(s))
    return "\n".join(out) + "\n"


async def _stream_network_response(
    fetch_url: str,
    request: Request,
    media_id: int,
    url_id: int | None,
):
    """Fetch a network URL through the backend. HLS playlists are read fully,
    rewritten to route all sub-resources through the proxy; everything else is
    streamed (with Range support) untouched."""
    import httpx

    fwd_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
    }
    range_header = request.headers.get("range")
    if range_header:
        fwd_headers["Range"] = range_header

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(60.0, connect=10.0),
        follow_redirects=True,
        proxy=await get_proxy_url(),
    )
    try:
        req = client.build_request("GET", fetch_url, headers=fwd_headers)
        resp = await client.send(req, stream=True)

        if resp.status_code not in (200, 206):
            await resp.aclose()
            await client.aclose()
            raise HTTPException(
                status_code=502,
                detail=f"Network source returned {resp.status_code}",
            )

        content_type = resp.headers.get("content-type", "video/mp4")
        response_headers: dict[str, str] = {
            "Cache-Control": "no-cache",
            "Accept-Ranges": "bytes",
        }
        if "content-length" in resp.headers:
            response_headers["Content-Length"] = resp.headers["content-length"]
        if "content-range" in resp.headers:
            response_headers["Content-Range"] = resp.headers["content-range"]
        status_code = 206 if "content-range" in resp.headers else 200

        # HLS playlist: read fully and rewrite referenced resources to the proxy.
        if _is_hls(content_type, str(resp.url)):
            raw = await resp.aread()
            await resp.aclose()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("latin-1")
            rewritten = _rewrite_m3u8(text, media_id, url_id, str(resp.url))
            await client.aclose()
            return Response(
                content=rewritten,
                media_type="application/vnd.apple.mpegurl",
                headers=response_headers,
            )

        async def stream_response():
            try:
                async for chunk in resp.aiter_raw(chunk_size=1024 * 1024):
                    yield chunk
            finally:
                await resp.aclose()
                await client.aclose()

        return StreamingResponse(
            stream_response(),
            media_type=content_type,
            status_code=status_code,
            headers=response_headers,
        )
    except HTTPException:
        await client.aclose()
        raise
    except httpx.RequestError:
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail="Network request failed — URL may be unreachable",
        )
    except Exception:
        await client.aclose()
        raise


@router.get("/{media_id}/network-part")
async def network_part(
    media_id: int,
    request: Request,
    fetch: str = Query(...),
):
    """Proxy a fragment / nested playlist referenced by a proxied HLS manifest.

    Only allows fetching http(s) URLs whose host matches one of the media's
    known SOURCE-url hosts, to mitigate SSRF from arbitrary URLs.
    """
    import urllib.parse

    u = urllib.parse.urlparse(fetch)
    if u.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Invalid fragment URL")
    host = u.netloc.lower()

    async with async_session() as db:
        await _get_media_or_404(db, media_id)
        rows = await db.execute(
            select(MediaUrl.url).where(
                MediaUrl.media_id == media_id,
                MediaUrl.url_role == UrlRole.SOURCE,
            )
        )
        known_hosts = {
            urllib.parse.urlparse(r).netloc.lower()
            for r in rows.scalars()
            if r
        }
        if not known_hosts or host not in known_hosts:
            raise HTTPException(
                status_code=403, detail="Fragment host not allowed"
            )

    return await _stream_network_response(fetch, request, media_id, None)


@router.get("/{media_id}/network-stream")
async def stream_network_media(
    media_id: int,
    request: Request,
    url_id: int | None = None,
):
    """Proxy a network source URL for inline playback in the player.

    Solves CORS issues by streaming the network URL through the backend.
    Supports HTTP Range requests for video seeking.

    ``url_id`` selects a specific MediaUrl (multi-source switching); when
    omitted, the first playable source URL is used. Browser-like User-Agent
    is forwarded — several CDN sources 403 without it.

    Note: DB connection is released right after resolving the URL — the
    proxy stream can last minutes and must not hold the (single) SQLite
    connection, or every other request would time out waiting for the pool.
    """
    import httpx
    from app.models.media import MediaUrl
    from app.models.enums import UrlRole

    # Resolve the URL in a short-lived session, then release the connection
    # before streaming (see note above).
    async with async_session() as db:
        media = await _get_media_or_404(db, media_id)

        if url_id is not None:
            result = await db.execute(
                select(MediaUrl).where(
                    MediaUrl.id == url_id,
                    MediaUrl.media_id == media_id,
                    MediaUrl.url_role == UrlRole.SOURCE,
                )
            )
            url_obj = result.scalars().first()
        else:
            result = await db.execute(
                select(MediaUrl).where(
                    MediaUrl.media_id == media_id,
                    MediaUrl.url_role == UrlRole.SOURCE,
                    MediaUrl.is_expired == False,  # noqa: E712
                ).order_by(MediaUrl.created_at)
            )
            url_obj = result.scalars().first()
        if not url_obj:
            raise HTTPException(status_code=400, detail="No playable network source URL found")

        network_url = url_obj.url
        try:
            validate_http_url(network_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    # ---- connection released from here on ----
    return await _stream_network_response(network_url, request, media_id, url_obj.id)


@router.post("/{media_id}/extract-network-metadata")
async def extract_network_metadata(media_id: int):
    """Extract metadata (duration, codec, dimensions) from a network source URL.

    Uses ffprobe to analyze the network URL. Also generates a thumbnail
    from the network source using ffmpeg.

    Connection hygiene: reads URL in a short session, runs ffprobe/ffmpeg
    (up to 30s each) WITHOUT holding a connection, then writes back in a
    fresh session.
    """
    import asyncio
    import json
    from app.models.media import MediaUrl
    from app.models.enums import UrlRole
    from app.services.ffmpeg_utils import get_ffprobe, get_ffmpeg
    from app.config import settings as _cfg

    # Phase 1 — read media + URL, then release the connection.
    async with async_session() as db:
        media = await _get_media_or_404(db, media_id)

        result = await db.execute(
            select(MediaUrl).where(
                MediaUrl.media_id == media_id,
                MediaUrl.url_role == UrlRole.SOURCE,
                MediaUrl.is_expired == False,  # noqa: E712
            ).order_by(MediaUrl.created_at)
        )
        url_obj = result.scalars().first()
        if not url_obj:
            raise HTTPException(status_code=400, detail="No network source URL found")

        network_url = url_obj.url
        try:
            validate_http_url(network_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    # Phase 2 — ffprobe the network URL (no DB connection held).
    ffprobe = _get_ffprobe()

    duration = None
    width = None
    height = None
    codec = None
    fps = None
    bitrate = None

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            ffprobe,
            "-v", "error",
            "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,bit_rate",
            "-show_entries", "format=duration,bit_rate",
            "-of", "json",
            network_url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        if proc.returncode != 0:
            raise HTTPException(
                status_code=502,
                detail=f"ffprobe failed: {stderr.decode()[:200]}",
            )

        data = json.loads(stdout.decode())
        streams = data.get("streams", [])
        format_info = data.get("format", {})

        for stream in streams:
            if stream.get("codec_type") == "video":
                width = stream.get("width")
                height = stream.get("height")
                codec = stream.get("codec_name")
                fps_str = stream.get("r_frame_rate", "0/1")
                try:
                    num, denom = fps_str.split("/")
                    fps = float(num) / float(denom) if float(denom) > 0 else None
                except (ValueError, ZeroDivisionError):
                    pass
                break

        duration_str = format_info.get("duration")
        if duration_str:
            try:
                duration = float(duration_str)
            except ValueError:
                pass

        bitrate_raw = format_info.get("bit_rate")
        if bitrate_raw:
            try:
                bitrate = int(bitrate_raw)
            except (ValueError, TypeError):
                bitrate = None

    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Network source analysis timed out")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to extract metadata: {str(exc)[:200]}")
    finally:
        # wait_for() only cancels the coroutine; the child must be killed too.
        await _terminate_process(proc)

    # Generate thumbnail from network source (no DB connection held)
    thumb_path = None
    thumb_proc = None
    try:
        if duration and duration > 0:
            thumb_dir = _cfg.thumbnail_dir
            thumb_dir.mkdir(parents=True, exist_ok=True)
            candidate = thumb_dir / f"{media_id}_net.jpg"

            ffmpeg = _get_ffmpeg()
            seek_time = min(duration * 0.1, 10.0)

            thumb_proc = await asyncio.create_subprocess_exec(
                ffmpeg,
                "-ss", f"{seek_time:.3f}",
                "-i", network_url,
                "-frames:v", "1",
                "-vf", "scale=320:-1",
                "-q:v", "5",
                "-y",
                str(candidate),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(thumb_proc.communicate(), timeout=30)

            if candidate.is_file():
                thumb_path = str(candidate)
    except (asyncio.TimeoutError, Exception):
        # Thumbnail is best-effort; never fail the metadata extraction for it
        thumb_path = None
    finally:
        await _terminate_process(thumb_proc)

    # Phase 3 — write back in a fresh session.
    async with async_session() as db:
        media = await _get_media_or_404(db, media_id)

        if duration is not None:
            media.duration = duration
        if width is not None:
            media.width = width
        if height is not None:
            media.height = height
        if codec is not None:
            media.codec = codec
        if fps is not None:
            media.fps = fps
        if bitrate is not None:
            media.bitrate = bitrate

        if codec and not media.mime_type:
            if codec in ("h264", "avc", "avc1"):
                media.mime_type = "video/mp4"
            elif codec in ("vp8", "vp9", "av1"):
                media.mime_type = "video/webm"

        if thumb_path and not media.thumbnail_path:
            media.thumbnail_path = thumb_path

        await db.flush()

        thumbnail_generated = media.thumbnail_path is not None

    return {
        "success": True,
        "duration": duration,
        "width": width,
        "height": height,
        "codec": codec,
        "thumbnail_generated": thumbnail_generated,
    }


@router.get("/{media_id}/thumbnail")
async def get_thumbnail(media_id: int, db: AsyncSession = Depends(get_db)):
    """Get the media's thumbnail image."""
    media = await _get_media_or_404(db, media_id, allow_deleted=True)
    path = _resolve_asset_file(media.thumbnail_path, app_settings.thumbnail_dir / f"{media_id}.jpg")
    if path is None:
        raise HTTPException(status_code=404, detail="Thumbnail file not found on disk")
    if path != media.thumbnail_path:
        # Self-heal: DB path went stale (e.g. data-root migration) — rewrite it
        media.thumbnail_path = str(path)
        await db.commit()

    return FileResponse(
        str(path),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/{media_id}/contact-sheet")
async def get_contact_sheet(media_id: int, db: AsyncSession = Depends(get_db)):
    """Serve the media's 4×4 contact sheet (manual-trigger feature).

    Returns 404 until the user generates one from the detail/manage page.
    """
    await _get_media_or_404(db, media_id, allow_deleted=True)
    from app.services.contact_sheet import contact_sheet_path

    path = contact_sheet_path(media_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Contact sheet not generated yet")
    return FileResponse(
        str(path),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post("/{media_id}/contact-sheet")
async def generate_media_contact_sheet(media_id: int, db: AsyncSession = Depends(get_db)):
    """Generate (or regenerate) the 16-frame 4×4 contact sheet for one media."""
    media = await _get_media_or_404(db, media_id)
    if media.is_deleted:
        raise HTTPException(status_code=400, detail="已在回收站")
    if media.file_missing or not media.file_path:
        raise HTTPException(status_code=400, detail="无本地文件或文件缺失")

    from app.services.contact_sheet import contact_sheet_path, generate_contact_sheet

    ok = await generate_contact_sheet(
        media.file_path, media.id, float(media.duration or 0)
    )
    if not ok:
        raise HTTPException(status_code=500, detail="缩略图集生成失败")

    return {
        "success": True,
        "url": f"/media/{media.id}/contact-sheet",
        "path": str(contact_sheet_path(media.id)),
    }


@router.get("/{media_id}/related")
async def get_related_media(
    media_id: int,
    limit: int = Query(8, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
):
    """播放结束推荐：同系列下一集 > 同标签 > 同库，排除自身/回收站/受限库。

    Returns ``{ items: [{id, title, year, duration, has_thumbnail, reason}] }``
    where reason ∈ {series, tag, library}（按优先级顺序填充，截断到 limit）。
    """
    media = await _get_media_or_404(db, media_id)
    restricted_ids = await get_restricted_library_ids(db)
    picked: dict[int, dict] = {}

    def _allowed(m: Media) -> bool:
        if m.id == media_id or m.is_deleted:
            return False
        if restricted_ids and m.library_id in restricted_ids:
            return False
        return m.id not in picked

    def _pick(rows: list[Media], reason: str) -> None:
        for m in rows:
            if len(picked) >= limit:
                break
            if not _allowed(m):
                continue
            thumb_ok = bool(m.thumbnail_path) or (
                app_settings.thumbnail_dir / f"{m.id}.jpg"
            ).is_file()
            picked[m.id] = {
                "id": m.id,
                "title": m.title,
                "year": m.year,
                "duration": m.duration,
                "has_thumbnail": thumb_ok,
                "reason": reason,
            }

    # 1) 同系列（季/集排序，下一集自然靠前）
    if media.series_id:
        result = await db.execute(
            select(Media)
            .where(
                Media.series_id == media.series_id,
                Media.id != media_id,
                Media.is_deleted == False,  # noqa: E712
            )
            .order_by(Media.season_number, Media.episode_number)
        )
        _pick(list(result.scalars().all()), "series")

    # 2) 同标签（OR 语义，按共同标签数降序）
    if len(picked) < limit:
        tag_ids = (
            await db.execute(select(VideoTag.tag_id).where(VideoTag.media_id == media_id))
        ).scalars().all()
        if tag_ids:
            result = await db.execute(
                select(Media)
                .join(VideoTag, VideoTag.media_id == Media.id)
                .where(
                    VideoTag.tag_id.in_(tag_ids),
                    Media.id != media_id,
                    Media.is_deleted == False,  # noqa: E712
                )
                .group_by(Media.id)
                .order_by(func.count(VideoTag.tag_id).desc())
                .limit(limit * 2)
            )
            _pick(list(result.scalars().all()), "tag")

    # 3) 同库兜底（最近添加优先）
    if len(picked) < limit:
        result = await db.execute(
            select(Media)
            .where(
                Media.library_id == media.library_id,
                Media.id != media_id,
                Media.is_deleted == False,  # noqa: E712
            )
            .order_by(Media.created_at.desc())
            .limit(limit)
        )
        _pick(list(result.scalars().all()), "library")

    return {"items": list(picked.values())[:limit]}


@router.get("/{media_id}/poster")
async def get_poster(media_id: int, db: AsyncSession = Depends(get_db)):
    """Get the media's scraped poster image (falls back to 404 if not scraped)."""
    media = await _get_media_or_404(db, media_id, allow_deleted=True)
    fallback: Path | None = None
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        candidate = app_settings.poster_dir / f"{media_id}{ext}"
        if candidate.is_file():
            fallback = candidate
            break
    path = _resolve_asset_file(media.poster_path, fallback)
    if path is None:
        raise HTTPException(status_code=404, detail="Poster file not found on disk")
    if path != media.poster_path:
        media.poster_path = str(path)
        await db.commit()

    return FileResponse(
        str(path),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/{media_id}/backdrop")
async def get_backdrop(media_id: int, db: AsyncSession = Depends(get_db)):
    """Return the scraped TMDB backdrop (movie/tv only).

    Backdrops are not downloaded at scrape time: the first request fetches
    from the configured TMDB image source and caches the file under
    backdrop_dir/{media_id}.jpg. AV media has no backdrop_path and 404s.
    """
    media = await _get_media_or_404(db, media_id)
    sd = media.scrape_data or {}
    rel = sd.get("backdrop_path")
    if not isinstance(rel, str) or not rel.strip():
        raise HTTPException(status_code=404, detail="No backdrop available")
    rel = rel.strip()
    suffix = Path(rel).suffix.lower()
    if (
        not rel.startswith("/")
        or ".." in rel
        or any(ch in rel for ch in ("?", "#", ":", "\\"))
        or suffix not in (".jpg", ".jpeg", ".png", ".webp")
    ):
        raise HTTPException(status_code=404, detail="Invalid backdrop path")

    app_settings.backdrop_dir.mkdir(parents=True, exist_ok=True)
    cache = app_settings.backdrop_dir / f"{media_id}.jpg"
    headers = {"Cache-Control": "public, max-age=604800"}
    if cache.is_file():
        return FileResponse(str(cache), media_type="image/jpeg", headers=headers)

    import httpx
    from app.services.scraper import _load_tmdb_config_from_db

    try:
        cfg = await _load_tmdb_config_from_db()
        url = f"{cfg.image_base.rstrip('/')}{rel}"
        async with httpx.AsyncClient(timeout=30, proxy=await get_proxy_url()) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        cache.write_bytes(resp.content)
    except (httpx.HTTPError, OSError) as exc:
        raise HTTPException(
            status_code=502, detail=f"Failed to fetch backdrop: {str(exc)[:120]}"
        )
    return FileResponse(
        str(cache),
        media_type=resp.headers.get("content-type", "image/jpeg"),
        headers=headers,
    )


@router.post("/{media_id}/poster")
async def upload_poster(
    media_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a custom poster/cover image for a media item.

    Accepts common image formats (jpg, png, webp). The file is saved to
    the poster directory and media.poster_path is updated.
    """
    media = await _get_media_or_404(db, media_id)

    # Validate content type
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    content_type = (file.content_type or "").lower()
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式: {file.content_type}。请上传 JPG/PNG/WebP 图片",
        )

    # Determine file extension from content type
    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }
    ext = ext_map.get(content_type, ".jpg")

    # Save to poster directory
    from app.config import settings as _cfg
    _cfg.poster_dir.mkdir(parents=True, exist_ok=True)

    # Delete old poster file if it exists (guarded to managed asset roots).
    if media.poster_path:
        if _is_within_asset_root(media.poster_path):
            old_path = Path(media.poster_path)
            if old_path.is_file():
                try:
                    old_path.unlink()
                except OSError:
                    pass  # Ignore deletion errors

    # Save new poster
    poster_filename = f"{media_id}{ext}"
    poster_path = _cfg.poster_dir / poster_filename

    max_bytes = 20 * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="图片过大（最大 20MB）")
    await asyncio.to_thread(poster_path.write_bytes, content)

    # Update database
    media.poster_path = str(poster_path)
    # 标记为用户上传封面：后续刮削不会用源站封面覆盖它
    media.poster_source = "custom"
    await db.flush()

    return {
        "success": True,
        "poster_path": str(poster_path),
        "poster_url": f"/api/media/{media_id}/poster?t={int(datetime.now(timezone.utc).timestamp())}",
    }


@router.post("/{media_id}/poster-from-frame")
async def poster_from_frame(
    media_id: int,
    t: float = Query(0, ge=0, description="Timestamp in seconds (player currentTime)"),
    db: AsyncSession = Depends(get_db),
):
    """Extract the video frame at timestamp t and set it as the media's cover.

    Server-side ffmpeg extraction from the ORIGINAL local file — no canvas
    taint concerns, full resolution, and the exact frame the user paused on.
    Marks poster_source="custom" so subsequent scrapes won't overwrite it.
    """
    media = await _get_media_or_404(db, media_id)
    if not media.file_path:
        raise HTTPException(status_code=400, detail="网络视频暂不支持从当前帧生成封面")
    if media.file_missing:
        raise HTTPException(status_code=410, detail="本地文件已丢失")
    path = Path(media.file_path)
    if not path.is_file():
        raise HTTPException(status_code=410, detail="本地文件不存在")

    # Clamp to valid range (mirror the screenshot endpoint)
    duration = media.duration or 0
    timestamp = max(0, min(t, duration - 0.1)) if duration > 0 else max(0, t)

    from app.config import settings as _cfg
    from app.services.thumbnail import _generate_thumbnail_sync

    _cfg.poster_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = _cfg.poster_dir / f"{media_id}_frame_tmp.jpg"

    # Exact-frame extraction: smart_frame forcibly disabled so the frame is
    # precisely the one the user paused on (never a "nicer" candidate).
    # Cap width at the source resolution (never upscale), max 1920.
    cover_w = min(1920, media.width) if (media.width or 0) > 0 else 1920
    success = await asyncio.to_thread(
        _generate_thumbnail_sync,
        str(path),
        str(tmp_path),
        timestamp,
        cover_w,
        95,
        False,  # smart_frame=False — user picked this exact frame
        duration,
    )
    if not success or not tmp_path.is_file():
        raise HTTPException(status_code=500, detail="帧提取失败，请稍后重试")

    # Replace old poster (guarded to managed asset roots) only after success
    if media.poster_path and _is_within_asset_root(media.poster_path):
        old_path = Path(media.poster_path)
        if old_path.is_file() and old_path != tmp_path:
            try:
                old_path.unlink()
            except OSError:
                pass

    final_path = _cfg.poster_dir / f"{media_id}.jpg"
    if final_path != tmp_path:
        await asyncio.to_thread(tmp_path.replace, final_path)

    media.poster_path = str(final_path)
    media.poster_source = "custom"  # 后续刮削不会覆盖用户自选封面
    await db.flush()

    return {
        "success": True,
        "poster_path": str(final_path),
        "poster_url": f"/api/media/{media_id}/poster?t={int(datetime.now(timezone.utc).timestamp())}",
    }


@router.delete("/{media_id}/poster")
async def delete_poster(
    media_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Remove custom poster/cover image from a media item."""
    media = await _get_media_or_404(db, media_id)

    if not media.poster_path:
        raise HTTPException(status_code=404, detail="该媒体没有封面图")

    # S1: only ever delete files inside the managed asset directories
    if not _is_within_asset_root(media.poster_path):
        raise HTTPException(status_code=400, detail="封面路径无效，已拒绝删除")

    # Delete file
    old_path = Path(media.poster_path)
    if old_path.is_file():
        try:
            old_path.unlink()
        except OSError:
            pass

    media.poster_path = None
    media.poster_source = None  # 删除封面后，下次刮削可重新从源站下载
    await db.flush()

    return {"success": True, "message": "封面图已删除"}


@router.get("/{media_id}/screenshot")
async def get_screenshot(
    media_id: int,
    t: float = Query(0, ge=0, description="Timestamp in seconds"),
    db: AsyncSession = Depends(get_db),
):
    """Extract a single video frame at timestamp t and return as JPEG.

    Uses ffmpeg to seek to the given position and extract one frame.
    Results are cached on disk per (media_id, rounded_second) to avoid
    repeated ffmpeg subprocess calls for the same preview position.
    """
    media = await _get_media_or_404(db, media_id)
    if not media.file_path:
        raise HTTPException(status_code=400, detail="Media has no local file path")
    if media.file_missing:
        raise HTTPException(status_code=410, detail="本地文件已丢失")
    path = Path(media.file_path)
    if not path.is_file():
        raise HTTPException(status_code=410, detail="Media file not found on disk")

    # Clamp timestamp to valid range
    duration = media.duration or 0
    if duration > 0:
        timestamp = max(0, min(t, duration - 0.1))
    else:
        timestamp = max(0, t)

    # Disk cache: thumbnails/screenshots/{media_id}/{rounded_second}.jpg
    cache_dir = _settings.thumbnail_dir / "screenshots" / str(media_id)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{int(round(timestamp))}.jpg"

    if not cache_file.is_file():
        success = await _generate_thumbnail(
            str(path),
            str(cache_file),
            time_offset=timestamp,
            size=320,
            quality=70,
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to extract frame")

    return FileResponse(
        str(cache_file),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.post("/{media_id}/scrape", response_model=MediaResponse)
async def scrape_single_media(media_id: int, db: AsyncSession = Depends(get_db)):
    """Scrape a single media item from TMDB and return the updated record.

    Populates title / year / description (overview) / poster_path. Raises 400
    when TMDB is not configured, 404 when no match is found, and 502 on a
    provider/network error.
    """
    # Prevent duplicate concurrent scrape requests for the same media
    if media_id in _scraping_media_ids:
        raise HTTPException(status_code=409, detail="该媒体正在刮削中，请稍后")
    _scraping_media_ids.add(media_id)

    try:
        await _get_media_or_404(db, media_id)

        from app.services.scraper import scrape_media, TMDBConfigError
        import httpx

        try:
            result = await scrape_media(media_id)
        except TMDBConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except httpx.HTTPError as exc:  # noqa: BLE001
            import logging
            logging.getLogger("vitoice").warning("TMDB request failed for media %s: %s", media_id, exc)
            raise HTTPException(status_code=502, detail="TMDB 请求失败，请检查网络或 API 配置")

        if not result.matched:
            raise HTTPException(status_code=404, detail=result.message or "未找到匹配")

        # Tags were created in a separate session by the scraper. Commit the
        # current transaction so the subsequent query sees the new data
        # (SQLite transaction isolation hides uncommitted writes from other
        # sessions, and even from the same session's older transaction).
        await db.commit()

        # Return the refreshed media record with relationships eagerly loaded.
        query = (
            select(Media)
            .where(Media.id == media_id)
            .options(
                *_MEDIA_DETAIL_LOADERS,
            )
        )
        result_q = await db.execute(query)
        media = result_q.scalar_one_or_none()
        if not media:
            raise HTTPException(status_code=404, detail="Media not found")
        resp = MediaResponse.model_validate(media)
        resp.tags = [TagResponse.model_validate(vt.tag) for vt in media.video_tags]
        return resp
    finally:
        _scraping_media_ids.discard(media_id)


@router.post("/{media_id}/progress", response_model=ProgressResponse)
async def update_playback_progress(
    media_id: int,
    payload: PlaybackProgressUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update playback progress for a media item.

    Automatically marks the media as watched if the position reaches 95% of
    the total duration. Returns a lightweight response (position + is_watched)
    instead of the full MediaResponse to reduce serialization overhead.
    """
    media = await _get_media_or_404(db, media_id)
    media.playback_position = payload.position
    media.last_played_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if payload.speed is not None:
        media.playback_speed = payload.speed
    if payload.is_watched is not None:
        media.is_watched = payload.is_watched
    elif media.duration and payload.position >= media.duration * 0.95:
        media.is_watched = True

    await db.flush()
    return ProgressResponse(
        position=media.playback_position,
        is_watched=media.is_watched,
    )
