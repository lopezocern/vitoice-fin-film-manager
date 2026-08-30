"""Recycle bin routes — soft-deleted media management.

Media records are soft-deleted (is_deleted=True) rather than physically
removed. This module provides endpoints to list, restore, permanently
delete, and empty the recycle bin.

When restoring, if the media was marked file_missing, the system checks
whether the file has been recovered on disk and restores the media_type
accordingly.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.enums import MediaType, UrlRole
from app.models.media import Media, MediaUrl
from app.models.library import MediaLibrary
from app.services.restricted import get_restricted_library_ids
from app.services.assets import cleanup_asset_files
from app.schemas.media import MediaListResponse, MediaResponse

router = APIRouter(prefix="/recycle-bin", tags=["recycle-bin"])


async def _get_deleted_media_or_404(db: AsyncSession, media_id: int) -> Media:
    """Get a soft-deleted media item or 404."""
    media = await db.get(Media, media_id)
    if not media or not media.is_deleted:
        raise HTTPException(status_code=404, detail="Media not found in recycle bin")
    return media


@router.get("", response_model=MediaListResponse)
async def list_recycle_bin(
    library_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_order: str = Query("desc"),
    db: AsyncSession = Depends(get_db),
):
    """List all soft-deleted media, sorted by deletion time."""
    query = select(Media).where(Media.is_deleted == True)  # noqa: E712

    if library_id is not None:
        query = query.where(Media.library_id == library_id)

    # Content restriction filter
    restricted_ids = await get_restricted_library_ids(db)
    if restricted_ids:
        query = query.where(~Media.library_id.in_(restricted_ids))

    # Total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Sorting by deletion time
    if sort_order.lower() == "asc":
        query = query.order_by(Media.deleted_at.asc())
    else:
        query = query.order_by(Media.deleted_at.desc())

    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    media_list = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return MediaListResponse(
        items=[MediaResponse.model_validate(m) for m in media_list],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("/{media_id}/restore", response_model=MediaResponse)
async def restore_media(
    media_id: int,
    target_library_id: int | None = Query(None, description="Override library if original was deleted"),
    db: AsyncSession = Depends(get_db),
):
    """Restore a soft-deleted media item.

    - If the original library still exists, media is restored to it.
    - If the library was deleted, ``target_library_id`` must be provided;
      otherwise a 400 error is returned.
    """
    media = await _get_deleted_media_or_404(db, media_id)

    # Check if original library still exists
    library = await db.get(MediaLibrary, media.library_id)
    if not library:
        if target_library_id is None:
            raise HTTPException(
                status_code=400,
                detail="Original library was deleted. Provide target_library_id to restore to a different library.",
            )
        target_lib = await db.get(MediaLibrary, target_library_id)
        if not target_lib:
            raise HTTPException(
                status_code=404, detail="Target library not found"
            )
        # uq_media_library_file: the target library must not already hold a
        # row (incl. another soft-deleted one) with the same file_path.
        if media.file_path:
            dup = await db.execute(
                select(Media.id).where(
                    Media.library_id == target_library_id,
                    Media.file_path == media.file_path,
                    Media.id != media.id,
                )
            )
            if dup.scalar_one_or_none():
                raise HTTPException(
                    status_code=409,
                    detail="目标资源库已存在相同文件路径的记录，无法恢复",
                )
        media.library_id = target_library_id

    media.is_deleted = False
    media.deleted_at = None

    # If the media was marked file_missing, check if the file has been recovered
    if media.file_missing and media.file_path:
        file_path = Path(media.file_path)
        if file_path.is_file():
            # File is back — clear file_missing and restore media_type
            media.file_missing = False
            media.missing_detected_at = None
            # Check for network source URLs to determine correct type
            net_result = await db.execute(
                select(MediaUrl.media_id)
                .where(
                    MediaUrl.media_id == media.id,
                    MediaUrl.url_role == UrlRole.SOURCE,
                )
                .limit(1)
            )
            has_network = net_result.fetchone() is not None
            media.media_type = MediaType.BOTH if has_network else MediaType.LOCAL

    await db.flush()
    await db.refresh(media)
    return MediaResponse.model_validate(media)


@router.post("/{media_id}/purge-local", response_model=MediaResponse)
async def purge_local_file(
    media_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete ONLY the local file of a soft-deleted media item.

    Keeps the media record + network sources and restores the media back to
    the library as a virtual network file (OFFLINE): title / tags / metadata /
    network sources are all preserved — only the playback method changes.

    This is the second confirmation step of the two-step delete flow:
      1. detail 页【回收】→ soft-delete into recycle bin (disk file untouched)
      2. recycle bin → 仅删本地文件 → purge disk file + restore as network file
    Requires a network source — otherwise deleting the file leaves nothing
    playable (the frontend only offers this option when one exists).
    """
    media = await _get_deleted_media_or_404(db, media_id)

    # Guard: must have a local file (operation precondition, not a policy gate)
    if media.file_missing or not media.file_path:
        raise HTTPException(status_code=400, detail="该媒体没有本地文件可删除")

    # Guard: must have a playable network source — this option's whole point
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
            detail="该媒体没有可用的网络源，无法仅删除本地文件",
        )

    # Delete the physical file (irreversible — recycle-bin second confirmation)
    path = Path(media.file_path)
    if path.is_file():
        try:
            path.unlink()
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"删除文件失败：{exc}")

    # Mark offline — keep file_path for diagnostics, flip flags
    media.file_missing = True
    if media.media_type in (MediaType.LOCAL, MediaType.BOTH):
        media.media_type = MediaType.OFFLINE

    # Restore: media comes back to the library as a virtual network file
    media.is_deleted = False
    media.deleted_at = None

    await db.flush()
    await db.refresh(media)
    return MediaResponse.model_validate(media)


@router.delete("/{media_id}/permanent", status_code=204)
async def permanent_delete_media(
    media_id: int,
    delete_file: bool = Query(False, description="Also delete the physical file"),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a media record from the database.

    The physical file is preserved unless ``delete_file=true`` is explicitly
    requested. This is irreversible.
    """
    media = await _get_deleted_media_or_404(db, media_id)

    # Optionally delete the main physical file
    if delete_file and media.file_path:
        file_path = Path(media.file_path)
        if file_path.is_file():
            try:
                file_path.unlink()
            except OSError:
                pass  # Best-effort; don't fail the DB deletion

    # Always clean up thumbnail and poster files (assets are useless without the record)
    cleanup_asset_files(media)

    await db.delete(media)
    await db.flush()


@router.post("/empty")
async def empty_recycle_bin(
    older_than_days: int | None = Query(None, description="Only delete items older than N days"),
    delete_files: bool = Query(False, description="Also delete physical files"),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete all (or old) items in the recycle bin.

    Returns the number of items deleted.
    """
    query = select(Media).where(Media.is_deleted == True)  # noqa: E712

    if older_than_days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        # SQLite stores naive datetimes; compare without timezone
        query = query.where(Media.deleted_at < cutoff.replace(tzinfo=None))

    result = await db.execute(query)
    media_list = result.scalars().all()

    count = 0
    for media in media_list:
        # Optionally delete the main physical file
        if delete_files and media.file_path:
            file_path = Path(media.file_path)
            if file_path.is_file():
                try:
                    file_path.unlink()
                except OSError:
                    pass
        # Always clean up thumbnail and poster files
        cleanup_asset_files(media)
        await db.delete(media)
        count += 1

    await db.flush()
    return {"deleted_count": count}
