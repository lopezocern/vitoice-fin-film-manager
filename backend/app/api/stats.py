"""Statistics endpoints — dashboard summary data."""
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.media import Media, VideoTag
from app.models.library import MediaLibrary
from app.models.task import Task
from app.models.enums import MediaType, TaskStatus
from app.services.restricted import get_restricted_library_ids
from app.schemas.common import ORMBaseModel

router = APIRouter(prefix="/stats", tags=["stats"])


def _mask_path(value: str | None) -> str | None:
    """Mask absolute filesystem paths the same way MediaResponse does."""
    if not value:
        return value
    parts = Path(value).parts
    if len(parts) <= 2:
        return value
    return str(Path("...") / Path(*parts[-2:]))


class StatsSummary(ORMBaseModel):
    """Dashboard summary statistics."""
    media_count: int
    library_count: int
    total_size: int  # bytes
    unorganized_count: int  # not watched AND no rating AND no tags
    running_tasks: int
    deleted_count: int  # recycle bin
    # --- 二期升级：问题导向计数（资产概览健康条 / 问题卡）---
    missing_count: int = 0  # file_missing=true
    no_poster_count: int = 0  # no poster and no thumbnail (episodes excluded)
    no_metadata_count: int = 0  # no scrape_data (episodes excluded)
    # --- 媒体管理来源统计（侧边栏来源区）---
    local_count: int = 0  # 有本地文件（local/both 且未缺失）
    network_count: int = 0  # 网络媒体（network/both）


class LibraryHealth(ORMBaseModel):
    """Per-library health for the dashboard library cards."""
    library_id: int
    name: str
    media_count: int
    missing_count: int
    total_size: int  # bytes


class RecentMedia(ORMBaseModel):
    id: int
    title: str
    thumbnail_path: str | None
    poster_path: str | None
    created_at: str | None
    library_id: int


class StatsResponse(ORMBaseModel):
    summary: StatsSummary
    recent_media: list[RecentMedia]
    library_health: list[LibraryHealth] = []


@router.get("/summary", response_model=StatsResponse)
async def get_stats_summary(db: AsyncSession = Depends(get_db)):
    """Get dashboard summary: counts, storage, recent media, running tasks."""
    # Content restriction filter
    restricted_ids = await get_restricted_library_ids(db)

    # Media count (excluding soft-deleted)
    media_query = select(func.count(Media.id)).where(Media.is_deleted == False)  # noqa: E712
    if restricted_ids:
        media_query = media_query.where(~Media.library_id.in_(restricted_ids))
    result = await db.execute(media_query)
    media_count = result.scalar() or 0

    # Library count (exclude restricted libraries if hidden)
    lib_query = select(func.count(MediaLibrary.id))
    if restricted_ids:
        lib_query = lib_query.where(~MediaLibrary.id.in_(restricted_ids))
    result = await db.execute(lib_query)
    library_count = result.scalar() or 0

    # Total storage size
    size_query = select(func.coalesce(func.sum(Media.file_size), 0)).where(
        Media.is_deleted == False  # noqa: E712
    )
    if restricted_ids:
        size_query = size_query.where(~Media.library_id.in_(restricted_ids))
    result = await db.execute(size_query)
    total_size = result.scalar() or 0

    # Unorganized: not watched AND no rating AND no tags
    unorg_query = select(func.count(Media.id)).where(
        Media.is_deleted == False,  # noqa: E712
        Media.is_watched == False,  # noqa: E712
        Media.rating.is_(None),
        ~Media.id.in_(
            select(VideoTag.media_id).distinct()
        ),
    )
    if restricted_ids:
        unorg_query = unorg_query.where(~Media.library_id.in_(restricted_ids))
    result = await db.execute(unorg_query)
    unorganized_count = result.scalar() or 0

    # Running tasks
    result = await db.execute(
        select(func.count(Task.id)).where(
            Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])
        )
    )
    running_tasks = result.scalar() or 0

    # Recycle bin count
    recycle_query = select(func.count(Media.id)).where(Media.is_deleted == True)  # noqa: E712
    if restricted_ids:
        recycle_query = recycle_query.where(~Media.library_id.in_(restricted_ids))
    result = await db.execute(recycle_query)
    deleted_count = result.scalar() or 0

    # --- 二期升级：问题导向计数 ---
    # Episode rows (series_id set) inherit poster/metadata from the parent
    # series, so they must not be reported as incomplete individually.
    # 纯网络媒体（NETWORK）无本地文件/海报是常态，不计入问题计数。
    base_issue = (
        Media.is_deleted == False,  # noqa: E712
        Media.series_id.is_(None),
        Media.media_type != MediaType.NETWORK,
    )
    missing_query = select(func.count(Media.id)).where(
        *base_issue, Media.file_missing == True  # noqa: E712
    )
    if restricted_ids:
        missing_query = missing_query.where(~Media.library_id.in_(restricted_ids))
    result = await db.execute(missing_query)
    missing_count = result.scalar() or 0

    no_poster_query = select(func.count(Media.id)).where(
        *base_issue,
        Media.poster_path.is_(None),
        Media.thumbnail_path.is_(None),
    )
    if restricted_ids:
        no_poster_query = no_poster_query.where(~Media.library_id.in_(restricted_ids))
    result = await db.execute(no_poster_query)
    no_poster_count = result.scalar() or 0

    # 口径与元数据工作台「待处理」一致：排除已忽略项，缺封面或缺元数据均计入。
    # 不排除网络媒体（NETWORK）——工作台待处理列表同样包含网络媒体。
    no_metadata_query = select(func.count(Media.id)).where(
        Media.is_deleted == False,  # noqa: E712
        Media.series_id.is_(None),
        Media.metadata_ignored == False,  # noqa: E712
        or_(Media.poster_path.is_(None), Media.scrape_data.is_(None)),
    )
    if restricted_ids:
        no_metadata_query = no_metadata_query.where(~Media.library_id.in_(restricted_ids))
    result = await db.execute(no_metadata_query)
    no_metadata_count = result.scalar() or 0

    # --- 媒体管理来源统计（侧边栏来源区）---
    # 本地文件：media_type 为 local/both 且 file_missing=false
    local_query = select(func.count(Media.id)).where(
        Media.is_deleted == False,  # noqa: E712
        Media.media_type.in_([MediaType.LOCAL, MediaType.BOTH]),
        Media.file_missing == False,  # noqa: E712
    )
    if restricted_ids:
        local_query = local_query.where(~Media.library_id.in_(restricted_ids))
    result = await db.execute(local_query)
    local_count = result.scalar() or 0

    # 网络媒体：media_type 为 network/both
    network_query = select(func.count(Media.id)).where(
        Media.is_deleted == False,  # noqa: E712
        Media.media_type.in_([MediaType.NETWORK, MediaType.BOTH]),
    )
    if restricted_ids:
        network_query = network_query.where(~Media.library_id.in_(restricted_ids))
    result = await db.execute(network_query)
    network_count = result.scalar() or 0

    # --- 二期升级：每库健康 ---
    library_rows = (
        select(
            MediaLibrary.id,
            MediaLibrary.name,
            func.count(Media.id).label("media_count"),
            func.coalesce(func.sum(Media.file_size), 0).label("total_size"),
        )
        .outerjoin(Media, (Media.library_id == MediaLibrary.id) & (Media.is_deleted == False))  # noqa: E712
        .group_by(MediaLibrary.id, MediaLibrary.name)
        .order_by(MediaLibrary.sort_order, MediaLibrary.created_at)
    )
    if restricted_ids:
        library_rows = library_rows.where(~MediaLibrary.id.in_(restricted_ids))
    result = await db.execute(library_rows)
    library_health = [
        LibraryHealth(
            library_id=row.id,
            name=row.name,
            media_count=row.media_count or 0,
            missing_count=0,
            total_size=row.total_size or 0,
        )
        for row in result.all()
    ]

    # Per-library missing counts (media rows not grouped into library rows above
    # because case() on missing needs its own aggregate).
    if library_health:
        missing_by_lib_query = (
            select(Media.library_id, func.count(Media.id).label("missing_count"))
            .where(Media.is_deleted == False, Media.file_missing == True)  # noqa: E712
            .group_by(Media.library_id)
        )
        if restricted_ids:
            missing_by_lib_query = missing_by_lib_query.where(~Media.library_id.in_(restricted_ids))
        result = await db.execute(missing_by_lib_query)
        missing_by_lib = {row.library_id: row.missing_count for row in result.all()}
        for entry in library_health:
            entry.missing_count = missing_by_lib.get(entry.library_id, 0)

    # Recent media (5 most recent)
    recent_query = (
        select(Media)
        .where(Media.is_deleted == False)  # noqa: E712
        .order_by(Media.created_at.desc())
        .limit(5)
    )
    if restricted_ids:
        recent_query = recent_query.where(~Media.library_id.in_(restricted_ids))
    result = await db.execute(recent_query)
    recent = result.scalars().all()
    recent_media = [
        RecentMedia(
            id=m.id,
            title=m.title,
            thumbnail_path=_mask_path(m.thumbnail_path),
            poster_path=_mask_path(m.poster_path),
            created_at=m.created_at.isoformat() if m.created_at else None,
            library_id=m.library_id,
        )
        for m in recent
    ]

    return StatsResponse(
        summary=StatsSummary(
            media_count=media_count,
            library_count=library_count,
            total_size=total_size,
            unorganized_count=unorganized_count,
            running_tasks=running_tasks,
            deleted_count=deleted_count,
            missing_count=missing_count,
            no_poster_count=no_poster_count,
            no_metadata_count=no_metadata_count,
            local_count=local_count,
            network_count=network_count,
        ),
        recent_media=recent_media,
        library_health=library_health,
    )
