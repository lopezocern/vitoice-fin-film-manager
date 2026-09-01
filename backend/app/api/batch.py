"""Batch operations on media — tag, untag, rating, delete, move, rename, scrape, thumbnail, export."""
import asyncio
import csv
import io
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.media import Media, VideoTag
from app.models.library import MediaLibrary
from app.models.series import Series
from app.models.enums import TaskPriority, TaskStatus, TaskType
from app.models.task import Task
from app.schemas.batch import (
    BatchActionRequest,
    BatchActionResponse,
    BatchFailedItem,
)
from app.services.restricted import get_restricted_library_ids

logger = logging.getLogger("vitoice.batch")

router = APIRouter(prefix="/media/batch", tags=["batch"])

# Keep strong references to background batch tasks to prevent premature GC
_active_batch_tasks: set[asyncio.Task] = set()


@router.post("", response_model=BatchActionResponse)
async def batch_action(
    payload: BatchActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Execute a batch operation on multiple media items.

    - **tag/untag/rating/delete/move/export**: synchronous, completed in one transaction.
    - **scrape/thumbnail**: asynchronous, creates a task and returns task_id.

    Partial failures do not roll back successful items; the response includes
    a ``failed`` list with per-item error details.
    """
    if payload.action in ("scrape", "thumbnail", "contact_sheet"):
        return await _create_batch_task(payload, db)

    media_ids = payload.media_ids
    failed: list[BatchFailedItem] = []
    success_count = 0

    # Fetch all target media (not filtered by is_deleted for batch ops)
    result = await db.execute(
        select(Media).where(Media.id.in_(media_ids))
    )
    media_map = {m.id: m for m in result.scalars().all()}

    # S7: batch ops must respect the restricted-content switch (no-op when
    # show_restricted is on — get_restricted_library_ids returns an empty set).
    restricted_ids = await get_restricted_library_ids(db)

    for idx, mid in enumerate(media_ids):
        media = media_map.get(mid)
        if not media:
            failed.append(BatchFailedItem(id=mid, error="Media not found"))
            continue
        if restricted_ids and media.library_id in restricted_ids:
            failed.append(BatchFailedItem(id=mid, error="受限内容已隐藏"))
            continue
        try:
            if payload.action == "tag":
                await _batch_tag(media, payload.params, db)
            elif payload.action == "untag":
                await _batch_untag(media, payload.params, db)
            elif payload.action == "rating":
                _batch_rating(media, payload.params)
            elif payload.action == "metadata_ignore":
                _batch_metadata_ignore(media, payload.params)
            elif payload.action == "delete":
                _batch_delete(media, payload.params)
            elif payload.action == "move":
                await _batch_move(media, payload.params, db)
            elif payload.action == "rename":
                await _batch_rename(media, payload.params, db, index=idx)
            success_count += 1
        except Exception as exc:  # noqa: BLE001
            failed.append(BatchFailedItem(id=mid, error=str(exc)))

    try:
        await db.flush()
    except IntegrityError:
        # Race window between the per-item pre-checks and this flush
        # (uq_media_library_file). Roll back the whole batch rather than 500.
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="批量操作遇到文件记录冲突，已整体回滚，请重试",
        )

    message = f"成功 {success_count}/{len(media_ids)}"
    if failed:
        message += f"，失败 {len(failed)}"

    return BatchActionResponse(
        action=payload.action,
        total=len(media_ids),
        success_count=success_count,
        failed=failed,
        message=message,
    )


@router.post("/export")
async def batch_export(
    payload: BatchActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Export selected media metadata as JSON or CSV file download."""
    fmt = payload.params.get("format", "json")
    media_ids = payload.media_ids

    result = await db.execute(
        select(Media).where(Media.id.in_(media_ids))
    )
    media_list = result.scalars().all()

    # S7: restricted libraries must not be exportable while hidden.
    restricted_ids = await get_restricted_library_ids(db)
    if restricted_ids:
        media_list = [m for m in media_list if m.library_id not in restricted_ids]

    rows = [
        {
            "id": m.id,
            "title": m.title,
            "file_name": m.file_name,
            "file_size": m.file_size,
            "duration": m.duration,
            "rating": m.rating,
            "is_favorite": m.is_favorite,
            "is_watched": m.is_watched,
            "library_id": m.library_id,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in media_list
    ]

    if fmt == "csv":
        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        content = output.getvalue()
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8-sig")),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=media_export.csv"
            },
        )
    else:
        content = json.dumps(rows, ensure_ascii=False, indent=2)
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="application/json",
            headers={
                "Content-Disposition": "attachment; filename=media_export.json"
            },
        )


async def _batch_tag(media: Media, params: dict, db: AsyncSession) -> None:
    """Add tags to a media item. Skips already-existing tags."""
    tag_ids = params.get("tag_ids", [])
    if not tag_ids:
        raise ValueError("tag_ids is required")
    for tag_id in tag_ids:
        # Check if already exists (unique constraint)
        existing = await db.execute(
            select(VideoTag).where(
                VideoTag.media_id == media.id,
                VideoTag.tag_id == tag_id,
            )
        )
        if not existing.scalar_one_or_none():
            db.add(VideoTag(
                media_id=media.id,
                tag_id=tag_id,
                source="manual",
                is_verified=True,
            ))


async def _batch_untag(media: Media, params: dict, db: AsyncSession) -> None:
    """Remove tags from a media item."""
    if params.get("all"):
        result = await db.execute(
            select(VideoTag).where(VideoTag.media_id == media.id)
        )
        for vt in result.scalars().all():
            await db.delete(vt)
    else:
        tag_ids = params.get("tag_ids", [])
        if not tag_ids:
            raise ValueError("tag_ids or all=true is required")
        result = await db.execute(
            select(VideoTag).where(
                VideoTag.media_id == media.id,
                VideoTag.tag_id.in_(tag_ids),
            )
        )
        for vt in result.scalars().all():
            await db.delete(vt)


def _batch_rating(media: Media, params: dict) -> None:
    """Set rating on a media item."""
    rating = params.get("rating")
    if rating is None:
        raise ValueError("rating is required")
    rating = int(rating)
    if not 1 <= rating <= 5:
        raise ValueError("rating must be 1-5")
    media.rating = rating


def _batch_metadata_ignore(media: Media, params: dict) -> None:
    """Ignore or un-ignore a media item in the metadata workspace.

    ``ignored`` defaults to True (mark as ignored); pass ``ignored: false``
    to restore the item back into the "incomplete metadata" list.
    """
    media.metadata_ignored = bool(params.get("ignored", True))


def _batch_delete(media: Media, params: dict) -> None:
    """Soft-delete a media item."""
    permanent = params.get("permanent", False)
    if permanent:
        # Will be handled by db.delete in flush
        raise NotImplementedError("Use permanent delete endpoint")
    media.is_deleted = True
    media.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)


async def _batch_move(media: Media, params: dict, db: AsyncSession) -> None:
    """Move media to a different library."""
    target_id = params.get("target_library_id")
    if not target_id:
        raise ValueError("target_library_id is required")
    target_id = int(target_id)
    target_lib = await db.get(MediaLibrary, target_id)
    if not target_lib:
        raise ValueError("Target library not found")
    # uq_media_library_file: (library_id, file_path) must stay unique — a
    # soft-deleted row with the same path in the target library blocks the
    # move, so pre-check instead of letting flush blow up the whole batch.
    if media.file_path:
        dup = await db.execute(
            select(Media.id).where(
                Media.library_id == target_id,
                Media.file_path == media.file_path,
                Media.id != media.id,
            )
        )
        if dup.scalar_one_or_none():
            raise ValueError("目标库已存在相同文件路径的记录")
    media.library_id = target_id


# ---- Batch rename helpers ----

_ILLEGAL_FILENAME_CHARS = set('<>:"/\\|?*')


def _render_rename_template(
    template: str,
    media: Media,
    index: int,
    library_name: str = "",
) -> str:
    """Render a rename template string into a new filename (without extension).

    Supported placeholders:
      {title}      — media title (falls back to filename stem)
      {year}       — release year
      {filename}   — original filename without extension
      {index}      — sequential index (1-based by default)
      {index:N}    — zero-padded index with N digits
      {library}    — library name
      {rating}     — star rating (0-5)
      {date}       — current date as YYYY-MM-DD
      {series}     — series title (empty if not a series episode)
      {season}     — season number, 2-digit zero-padded (e.g. 01)
      {episode}    — episode number, 2-digit zero-padded (e.g. 03)
    """
    stem = Path(media.file_name or "").stem if media.file_name else ""
    title = media.title or stem
    year = str(media.year) if media.year else ""
    rating = str(media.rating) if media.rating else "0"
    today = datetime.now().strftime("%Y-%m-%d")
    series_title = (media.series_title or "").strip()

    def _replace(match: re.Match) -> str:
        token = match.group(1)
        if token == "title":
            return title
        if token == "year":
            return year
        if token == "filename":
            return stem
        if token == "library":
            return library_name
        if token == "rating":
            return rating
        if token == "date":
            return today
        if token == "series":
            return series_title
        if token == "season":
            return str(media.season_number).zfill(2) if media.season_number else ""
        if token == "episode":
            return str(media.episode_number).zfill(2) if media.episode_number else ""
        if token == "index":
            return str(index)
        # {index:N} — zero-padded
        m = re.match(r"index:(\d+)", token)
        if m:
            width = int(m.group(1))
            return str(index).zfill(width)
        # Unknown token — keep as-is
        return match.group(0)

    return re.sub(r"\{([^}]+)\}", _replace, template)


def _validate_new_filename(name: str) -> str:
    """Validate a rendered filename — no path separators, no illegal chars."""
    if not name or not name.strip():
        raise ValueError("文件名不能为空")
    name = name.strip()
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError("文件名不能包含路径分隔符")
    bad = set(name) & _ILLEGAL_FILENAME_CHARS
    if bad:
        raise ValueError(f"文件名包含非法字符: {' '.join(sorted(bad))}")
    return name


async def _db_path_taken(
    db: AsyncSession, library_id: int, file_path: str, exclude_id: int
) -> bool:
    """True when any other media row (incl. soft-deleted) occupies file_path."""
    result = await db.execute(
        select(Media.id).where(
            Media.library_id == library_id,
            Media.file_path == file_path,
            Media.id != exclude_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def _resolve_series_title(db: AsyncSession, media: Media) -> str:
    """Series title for rename templates: series_title first, else lookup by series_id."""
    title = (media.series_title or "").strip()
    if not title and media.series_id:
        row = await db.execute(select(Series.title).where(Series.id == media.series_id))
        title = (row.scalar_one_or_none() or "").strip()
        if title:
            media.series_title = title
    return title


async def _batch_rename(
    media: Media, params: dict, db: AsyncSession, index: int = 0
) -> None:
    """Rename a media file on disk using a template pattern.

    The file extension is always preserved.

    D4: when ``auto_suffix`` is truthy (default), a name collision at the
    target path is resolved by appending ``(1)``, ``(2)`` … instead of
    failing the item. Pass ``auto_suffix: false`` to keep the strict
    fail-fast behavior.
    """
    template = params.get("template")
    if not template:
        raise ValueError("template is required")

    auto_suffix = params.get("auto_suffix", True)

    if not media.file_path or media.file_missing:
        raise ValueError("文件丢失或无本地路径")

    old_path = Path(media.file_path)
    if not old_path.is_file():
        raise ValueError("源文件在磁盘上未找到")

    start_index = int(params.get("start_index", 1))
    actual_index = start_index + index

    # Get library name
    lib = await db.get(MediaLibrary, media.library_id)
    lib_name = lib.name if lib else ""

    # Series fallback: episodes linked only by series_id may have empty
    # series_title — resolve once and cache back onto the row.
    await _resolve_series_title(db, media)

    new_stem = _render_rename_template(template, media, actual_index, lib_name)
    new_stem = _validate_new_filename(new_stem)

    # Preserve extension
    ext = old_path.suffix
    new_name = new_stem + ext
    new_path = old_path.parent / new_name

    # Skip if no change
    if new_path == old_path:
        return

    # D4: resolve collisions by appending (1)(2)... when auto_suffix is on
    if new_path.exists():
        if not auto_suffix:
            raise ValueError(f"目标文件已存在: {new_name}")
        counter = 1
        while new_path.exists():
            new_name = f"{new_stem}({counter}){ext}"
            new_path = old_path.parent / new_name
            counter += 1

    # uq_media_library_file: a soft-deleted DB row may occupy the target path
    # even though the file itself is gone from disk — resolve the same way.
    if auto_suffix:
        counter = 0
        while await _db_path_taken(db, media.library_id, str(new_path), media.id):
            counter += 1
            new_name = f"{new_stem}({counter}){ext}"
            new_path = old_path.parent / new_name
    elif await _db_path_taken(db, media.library_id, str(new_path), media.id):
        raise ValueError(f"目标路径已被其他记录占用: {new_name}")

    # Verify within library root
    if lib:
        try:
            from app.services.scanner import validate_root_path
            root = validate_root_path(lib.root_path)
            new_path.resolve().relative_to(root)
        except ValueError:
            raise ValueError("重命名后的路径超出库范围")
        except Exception:
            logger.warning("Path validation failed for rename (index %d)", index, exc_info=True)

    # Rename physical file
    import shutil
    try:
        old_path.rename(new_path)
    except OSError:
        try:
            shutil.move(str(old_path), str(new_path))
        except (OSError, shutil.Error) as exc:
            raise ValueError(f"文件重命名失败: {exc}")

    # Update DB record
    media.file_path = str(new_path)
    media.file_name = new_name


@router.post("/rename-preview")
async def batch_rename_preview(
    payload: BatchActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Preview batch rename results without applying changes.

    Returns a list of { id, old_name, new_name, error } for each media item.
    """
    if payload.action != "rename":
        raise HTTPException(status_code=400, detail="action must be 'rename'")

    template = payload.params.get("template")
    if not template:
        raise HTTPException(status_code=400, detail="template is required")

    auto_suffix = payload.params.get("auto_suffix", True)
    start_index = int(payload.params.get("start_index", 1))

    result = await db.execute(
        select(Media).where(Media.id.in_(payload.media_ids))
    )
    media_map = {m.id: m for m in result.scalars().all()}

    # S7: keep restricted titles out of rename previews while hidden.
    restricted_ids = await get_restricted_library_ids(db)

    # Preload library names
    lib_ids = {m.library_id for m in media_map.values()}
    lib_result = await db.execute(
        select(MediaLibrary).where(MediaLibrary.id.in_(lib_ids))
    )
    lib_map = {l.id: l.name for l in lib_result.scalars().all()}

    previews = []
    for idx, mid in enumerate(payload.media_ids):
        media = media_map.get(mid)
        if not media:
            previews.append({
                "id": mid,
                "old_name": "",
                "new_name": "",
                "error": "Media not found",
            })
            continue
        if restricted_ids and media.library_id in restricted_ids:
            previews.append({
                "id": mid,
                "old_name": "",
                "new_name": "",
                "error": "受限内容已隐藏",
            })
            continue

        old_name = media.file_name or ""
        ext = Path(old_name).suffix if old_name else ""

        try:
            await _resolve_series_title(db, media)
            new_stem = _render_rename_template(
                template, media, start_index + idx, lib_map.get(media.library_id, "")
            )
            new_stem = _validate_new_filename(new_stem)
            new_name = new_stem + ext

            # Check for conflicts — D4: auto_suffix resolves them by appending
            # (1)(2)...; the preview shows the actual filename that would be used.
            if media.file_path:
                old_path = Path(media.file_path)
                new_path = old_path.parent / new_name
                if new_path != old_path and new_path.exists():
                    if not auto_suffix:
                        raise ValueError(f"目标文件已存在: {new_name}")
                    counter = 1
                    while new_path.exists():
                        new_name = f"{new_stem}({counter}){ext}"
                        new_path = old_path.parent / new_name
                        counter += 1

            if not media.file_path or media.file_missing:
                raise ValueError("文件丢失或无本地路径")

            previews.append({
                "id": mid,
                "old_name": old_name,
                "new_name": new_name,
                "error": None,
            })
        except Exception as exc:
            previews.append({
                "id": mid,
                "old_name": old_name,
                "new_name": "",
                "error": str(exc),
            })

    return {"previews": previews}


async def _create_batch_task(
    payload: BatchActionRequest, db: AsyncSession
) -> BatchActionResponse:
    """Create an async task for scrape or thumbnail batch operations.

    The task is created and committed, then a background asyncio.Task is
    spawned to run the actual work.  The batch worker iterates over the
    specific media_ids (not a whole library) so it does not go through the
    task-manager dispatch loop.
    """
    action = payload.action
    media_ids = payload.media_ids

    if action == "scrape":
        task_type = TaskType.SCRAPE
        title = f"批量刮削 ({len(media_ids)} 个媒体)"
    elif action == "thumbnail":
        task_type = TaskType.THUMBNAIL
        title = f"批量生成缩略图 ({len(media_ids)} 个媒体)"
    elif action == "contact_sheet":
        task_type = TaskType.THUMBNAIL
        title = f"批量生成缩略图集 ({len(media_ids)} 个媒体)"
    else:
        raise ValueError(f"Unsupported async action: {action}")

    task = Task(
        type=task_type,
        status=TaskStatus.PENDING,
        priority=TaskPriority.MEDIUM,
        title=title,
        total=len(media_ids),
        current=0,
        progress=0,
        result=json.dumps({"media_ids": media_ids, "action": action}),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    task_id = task.id

    # Start background execution (keep strong reference to prevent GC collection
    # of the asyncio.Task before it completes).
    task = asyncio.create_task(_run_batch_async(task_id, media_ids, action))
    _active_batch_tasks.add(task)
    task.add_done_callback(_active_batch_tasks.discard)

    return BatchActionResponse(
        action=action,
        total=len(media_ids),
        success_count=0,
        task_id=task_id,
        message=f"已创建任务，共 {len(media_ids)} 个媒体待处理",
    )


async def _run_batch_async(
    task_id: int, media_ids: list[int], action: str
) -> None:
    """Background coroutine that runs a batch scrape or thumbnail job.

    Manages the full Task lifecycle: PENDING → RUNNING → COMPLETED/FAILED.
    """
    from app.database import async_session

    # Mark running
    try:
        async with async_session() as session:
            task = await session.get(Task, task_id)
            if task:
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
                await session.commit()
    except Exception:
        logger.warning("Failed to mark batch task %d as RUNNING", task_id, exc_info=True)

    result_msg: str
    try:
        result_msg = await _batch_worker(task_id, media_ids, action)
        # Mark completed
        async with async_session() as session:
            task = await session.get(Task, task_id)
            if task and task.status != TaskStatus.CANCELLED:
                task.status = TaskStatus.COMPLETED
                task.progress = 100
                task.current = len(media_ids)
                task.result = json.dumps(
                    {"media_ids": media_ids, "action": action, "message": result_msg}
                )
                task.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                await session.commit()
    except Exception as exc:
        async with async_session() as session:
            task = await session.get(Task, task_id)
            if task and task.status != TaskStatus.CANCELLED:
                task.status = TaskStatus.FAILED
                task.error_msg = str(exc)[:1000]
                task.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                await session.commit()


async def _batch_worker(task_id: int, media_ids: list[int], action: str) -> str:
    """Worker for async batch operations (scrape/thumbnail).

    Accepts plain values (not a TaskData object) because it is called
    directly via _run_batch_async rather than through the TaskManager
    dispatch loop.
    """
    from app.services.scraper import scrape_media
    from app.services.thumbnail import generate_thumbnail
    from app.database import async_session

    success: list[int] = []
    failed: list[dict] = []

    for i, media_id in enumerate(media_ids):
        try:
            async with async_session() as db:
                # Skip soft-deleted and metadata-ignored items (they must not
                # be scraped / re-thumbnailed from the recycle bin).
                media = await db.get(Media, media_id)
                if not media:
                    failed.append({"id": media_id, "error": "Media not found"})
                    continue
                if media.is_deleted:
                    failed.append({"id": media_id, "error": "已在回收站"})
                    continue
                if action == "scrape" and media.metadata_ignored:
                    failed.append({"id": media_id, "error": "已被用户忽略元数据"})
                    continue

                if action == "scrape":
                    result = await scrape_media(media_id)
                    if not result.matched:
                        failed.append(
                            {"id": media_id, "error": result.message or "未找到匹配"}
                        )
                    else:
                        success.append(media_id)
                elif action == "thumbnail":
                    media = await db.get(Media, media_id)
                    if media and media.file_path:
                        from app.config import settings
                        import os

                        output = os.path.join(
                            settings.thumbnail_dir, f"{media.id}.jpg"
                        )
                        ok = await generate_thumbnail(
                            media.file_path, output, duration=media.duration
                        )
                        if ok:
                            media.thumbnail_path = output
                            await db.commit()
                            success.append(media_id)
                        else:
                            failed.append(
                                {"id": media_id, "error": "缩略图生成失败"}
                            )
                    else:
                        failed.append({"id": media_id, "error": "无文件路径"})
                elif action == "contact_sheet":
                    from app.services.contact_sheet import generate_contact_sheet

                    if media.file_path and not media.file_missing:
                        ok = await generate_contact_sheet(
                            media.file_path, media.id, float(media.duration or 0)
                        )
                        if ok:
                            success.append(media_id)
                        else:
                            failed.append({"id": media_id, "error": "缩略图集生成失败"})
                    else:
                        failed.append({"id": media_id, "error": "无本地文件或文件缺失"})
        except Exception as exc:  # noqa: BLE001
            failed.append({"id": media_id, "error": str(exc)})

        # Update progress in the Task record
        try:
            async with async_session() as s:
                t = await s.get(Task, task_id)
                if t:
                    t.current = i + 1
                    t.progress = int((i + 1) / len(media_ids) * 100)
                    await s.commit()
        except Exception:
            logger.debug("Progress update failed for batch task %d", task_id, exc_info=True)

    result_msg = f"成功 {len(success)}/{len(media_ids)}"
    if failed:
        result_msg += f"，失败 {len(failed)}"
    return result_msg
