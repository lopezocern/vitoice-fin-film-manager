"""Library CRUD + scan API endpoints."""
import asyncio
import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.models.library import MediaLibrary
from app.models.media import Media, VideoTag
from app.models.tag import Tag
from app.models.enums import MediaType, TaskStatus, TaskType
from app.models.task import Task
from app.services.restricted import get_restricted_library_ids
from app.services.scanner import VIDEO_EXTENSIONS, validate_root_path
from app.schemas.library import (
    LibraryCreate,
    LibraryResponse,
    LibraryUpdate,
    mask_path,
)

logger = logging.getLogger("vitoice.api.libraries")
router = APIRouter(prefix="/libraries", tags=["libraries"])


async def _get_library_or_404(db: AsyncSession, library_id: int) -> MediaLibrary:
    lib = await db.get(MediaLibrary, library_id)
    if not lib:
        raise HTTPException(status_code=404, detail="Library not found")
    return lib


def _normalize_dir_path(raw: str) -> str:
    """Canonical form of a directory path for equality comparison.

    Folds case and normalizes separators/trailing slashes so that
    ``C:\\Media\\`` and ``c:/media`` compare equal. Needed because stored
    root_path values predate any normalization.
    """
    try:
        return os.path.normcase(os.path.normpath(os.path.abspath(raw)))
    except (OSError, ValueError):
        return os.path.normcase(str(raw).rstrip("\\/"))


async def _find_library_by_root_path(
    db: AsyncSession, root_path: str, *, exclude_id: int | None = None
) -> MediaLibrary | None:
    """Return the library already managing `root_path`, if any.

    Compares normalized paths rather than relying on exact string equality —
    libraries are few (well under a hundred), so scanning them in Python is
    cheaper than the false negatives an exact match would produce.
    """
    target = _normalize_dir_path(root_path)
    result = await db.execute(select(MediaLibrary))
    for lib in result.scalars().all():
        if exclude_id is not None and lib.id == exclude_id:
            continue
        if _normalize_dir_path(lib.root_path) == target:
            return lib
    return None


async def _count_media(db: AsyncSession, library_id: int) -> int:
    result = await db.execute(
        select(func.count(Media.id)).where(Media.library_id == library_id)
    )
    return result.scalar() or 0


def _to_response(lib: MediaLibrary, media_count: int = 0) -> LibraryResponse:
    """Convert ORM to response with masked root_path."""
    resp = LibraryResponse.model_validate({
        "id": lib.id,
        "name": lib.name,
        "root_path": mask_path(lib.root_path),
        "type": lib.type,
        "scrape_mode": lib.scrape_mode,
        # Coerce nullable boolean/int columns (DB may store NULL for rows
        # written before server_default was enforced) to satisfy the
        # required `bool`/`int` response fields.
        "is_restricted": bool(lib.is_restricted),
        "color": lib.color,
        "description": lib.description,
        "watch_enabled": bool(lib.watch_enabled),
        "auto_import": bool(lib.auto_import),
        "auto_mark_missing": bool(lib.auto_mark_missing),
        "auto_metadata": True,
        "auto_thumbnail": True,
        "sort_order": lib.sort_order or 0,
        "created_at": lib.created_at.isoformat() if lib.created_at else "",
        "updated_at": lib.updated_at.isoformat() if lib.updated_at else "",
        "media_count": media_count,
    })
    return resp


async def _enqueue_scan_if_idle(library_id: int, lib_name: str) -> dict:
    """Enqueue a scan task unless one is already pending/running."""
    async with async_session() as session:
        result = await session.execute(
            select(Task).where(
                Task.library_id == library_id,
                Task.type == TaskType.SCAN,
                Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
            )
        )
        existing = result.scalars().first()
    if existing:
        return {"status": "already_running", "task_id": existing.id}

    from app.tasks.manager import task_manager

    task_id = await task_manager.enqueue(
        task_type="scan",
        title=f"扫描库 · {lib_name}",
        library_id=library_id,
        priority="medium",
    )
    logger.info("Queued scan task %s for library %s", task_id, library_id)
    return {"status": "queued", "task_id": task_id}


@router.get("", response_model=list[LibraryResponse])
async def list_libraries(db: AsyncSession = Depends(get_db)):
    """List all libraries with media counts (single query, no N+1)."""
    query = (
        select(
            MediaLibrary,
            func.count(Media.id).label("media_count"),
        )
        .outerjoin(Media, MediaLibrary.id == Media.library_id)
        .group_by(MediaLibrary.id)
        .order_by(MediaLibrary.created_at)
    )

    # Content restriction filter
    restricted_ids = await get_restricted_library_ids(db)
    if restricted_ids:
        query = query.where(~MediaLibrary.id.in_(restricted_ids))

    result = await db.execute(query)
    libraries = []
    for lib, count in result.fetchall():
        libraries.append(_to_response(lib, count or 0))
    return libraries


@router.get("/{library_id}", response_model=LibraryResponse)
async def get_library(library_id: int, db: AsyncSession = Depends(get_db)):
    lib = await _get_library_or_404(db, library_id)
    count = await _count_media(db, library_id)
    return _to_response(lib, count)


@router.post("", response_model=LibraryResponse, status_code=201)
async def create_library(payload: LibraryCreate, db: AsyncSession = Depends(get_db)):
    # Reject a duplicate root_path before hitting the DB constraint: the
    # IntegrityError would surface as a 500, while this is a user error.
    # Registering the same directory twice would double-scan it into
    # duplicate media rows.
    duplicate = await _find_library_by_root_path(db, payload.root_path)
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail=f"该目录已被媒体库「{duplicate.name}」管理，不能重复添加",
        )

    lib = MediaLibrary(**payload.model_dump())
    db.add(lib)
    await db.commit()
    await db.refresh(lib)
    logger.info("Created library %s: %s", lib.id, lib.name)
    return _to_response(lib, 0)


@router.put("/{library_id}", response_model=LibraryResponse)
async def update_library(
    library_id: int, payload: LibraryUpdate, db: AsyncSession = Depends(get_db)
):
    lib = await _get_library_or_404(db, library_id)
    data = payload.model_dump(exclude_unset=True)
    if "root_path" in data and data["root_path"]:
        duplicate = await _find_library_by_root_path(
            db, data["root_path"], exclude_id=library_id
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=409,
                detail=f"该目录已被媒体库「{duplicate.name}」管理，不能重复添加",
            )
    for key, value in data.items():
        setattr(lib, key, value)
    await db.commit()
    await db.refresh(lib)
    count = await _count_media(db, library_id)
    return _to_response(lib, count)


@router.delete("/{library_id}")
async def delete_library(
    library_id: int,
    clean_empty_tags: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Delete a library and clean up orphaned tags by default.

    Cascade-deletes all media in the library. When ``clean_empty_tags=True``
    (default), tags that became orphaned (zero associations) after the deletion
    are also removed — but only non-builtin tags to preserve system tag types.
    """
    lib = await _get_library_or_404(db, library_id)

    # Check for running tasks on this library; cancel them
    result = await db.execute(
        select(Task).where(
            Task.library_id == library_id,
            Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
        )
    )
    active_tasks = result.scalars().all()

    if active_tasks:
        from app.tasks.manager import task_manager
        for t in active_tasks:
            await task_manager.cancel(t.id)
        logger.info("Cancelled %d active tasks for library %s", len(active_tasks), library_id)

    # Collect tag IDs associated with media in this library BEFORE deletion
    # so we can check which ones become orphaned afterwards.
    affected_tag_ids: set[int] = set()
    if clean_empty_tags:
        tag_result = await db.execute(
            select(VideoTag.tag_id)
            .join(Media, Media.id == VideoTag.media_id)
            .where(Media.library_id == library_id)
            .distinct()
        )
        affected_tag_ids = {row[0] for row in tag_result.fetchall()}

    await db.delete(lib)
    await db.commit()
    logger.info("Deleted library %s", library_id)

    # Clean up orphaned tags (zero associations after library deletion).
    # Removes ALL orphaned tags regardless of whether their TagType is builtin —
    # builtin protects the TagType (category), not individual tags within it.
    deleted_tags: list[dict] = []
    if clean_empty_tags and affected_tag_ids:
        for tag_id in affected_tag_ids:
            # Check if this tag still has any associations
            count_result = await db.execute(
                select(func.count()).select_from(
                    select(VideoTag).where(VideoTag.tag_id == tag_id).subquery()
                )
            )
            remaining = count_result.scalar() or 0
            if remaining == 0:
                tag = await db.get(Tag, tag_id)
                if tag:
                    deleted_tags.append({"id": tag.id, "name": tag.name})
                    await db.delete(tag)
        if deleted_tags:
            await db.commit()
            logger.info(
                "Cleaned up %d orphaned tags after library %s deletion",
                len(deleted_tags),
                library_id,
            )

    return {
        "status": "deleted",
        "library_id": library_id,
        "cleaned_tags": deleted_tags if clean_empty_tags else [],
        "cleaned_tags_count": len(deleted_tags) if clean_empty_tags else 0,
    }


@router.post("/{library_id}/scan")
async def scan_library(library_id: int):
    """Trigger a scan of the library.

    Prevents duplicate scans: checks for existing pending/running scan task.
    Uses short-lived sessions to avoid connection pool deadlock with
    task_manager.enqueue() (pool_size=1 constraint).
    """
    from app.database import async_session

    # Load library info in a short-lived session
    async with async_session() as session:
        lib = await session.get(MediaLibrary, library_id)
        if not lib:
            raise HTTPException(status_code=404, detail="Library not found")
        lib_id = lib.id
        lib_name = lib.name

    # Check for existing pending/running scan task (short-lived session)
    scan_info = await _enqueue_scan_if_idle(lib_id, lib_name)
    if scan_info["status"] == "already_running":
        return {
            "status": "already_running",
            "task_id": scan_info["task_id"],
            "library_id": lib_id,
            "library_name": lib_name,
            "message": "A scan is already in progress for this library",
        }

    return {
        "status": "queued",
        "task_id": scan_info["task_id"],
        "library_id": lib_id,
        "library_name": lib_name,
        "message": "Scan task queued",
    }


@router.post("/{library_id}/scrape")
async def scrape_library(
    library_id: int,
    re_scrape: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Trigger batch TMDB scraping for a library.

    By default only scrapes media without ``poster_path``. Set
    ``re_scrape=true`` to re-scrape all media in the library.
    """
    library = await _get_library_or_404(db, library_id)

    # Check for existing pending/running scrape task
    result = await db.execute(
        select(Task).where(
            Task.library_id == library_id,
            Task.type == TaskType.SCRAPE,
            Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
        )
    )
    existing = result.scalars().first()
    if existing:
        return {
            "status": "already_running",
            "task_id": existing.id,
            "message": "刮削任务正在运行中",
        }

    from app.tasks.manager import task_manager

    task_id = await task_manager.enqueue(
        task_type=TaskType.SCRAPE,
        title=f"批量刮削{' (重新)' if re_scrape else ''} · {library.name}",
        library_id=library.id,
        priority="medium",
    )

    # Store re_scrape flag so the worker can read it (H1 fix)
    task_record = await db.get(Task, task_id)
    if task_record:
        task_record.result = json.dumps({"re_scrape": re_scrape})
        await db.flush()

    logger.info("Queued scrape task %s for library %s (re_scrape=%s)", task_id, library.name, re_scrape)
    return {
        "status": "queued",
        "task_id": task_id,
        "library_id": library.id,
        "library_name": library.name,
        "message": "刮削任务已创建",
    }


@router.post("/{library_id}/ai-tags")
async def ai_tag_library(
    library_id: int,
    re_tag: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Trigger batch AI tagging for a library.

    By default only tags media without existing AI tags. Set
    ``re_tag=true`` to re-tag all media in the library.
    """
    library = await _get_library_or_404(db, library_id)

    # Check for existing pending/running AI tag task
    result = await db.execute(
        select(Task).where(
            Task.library_id == library_id,
            Task.type == TaskType.AI_TAG,
            Task.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
        )
    )
    existing = result.scalars().first()
    if existing:
        return {
            "status": "already_running",
            "task_id": existing.id,
            "message": "AI 打标任务正在运行中",
        }

    from app.tasks.manager import task_manager

    task_id = await task_manager.enqueue(
        task_type=TaskType.AI_TAG,
        title=f"批量 AI 打标{' (重新)' if re_tag else ''} · {library.name}",
        library_id=library.id,
        priority="low",
    )

    # Store re_tag flag so the worker can read it (H2 fix)
    task_record = await db.get(Task, task_id)
    if task_record:
        task_record.result = json.dumps({"re_tag": re_tag})
        await db.flush()

    logger.info("Queued AI tag task %s for library %s (re_tag=%s)", task_id, library.name, re_tag)
    return {
        "status": "queued",
        "task_id": task_id,
        "library_id": library.id,
        "library_name": library.name,
        "message": "AI 打标任务已创建",
    }


# ---------------------------------------------------------------------------
# File system directory tree — reflects actual folder structure on disk
# ---------------------------------------------------------------------------

class TreeNode(BaseModel):
    """A single node in the directory tree (directory or file)."""
    name: str
    rel_path: str  # relative to library root, using OS separator
    node_type: str  # "directory" | "file"
    size: int | None = None
    modified_at: float | None = None  # unix mtime (for time sorting)
    media_id: int | None = None
    is_scraped: bool = False
    has_poster: bool = False
    child_count: int | None = None  # immediate child count for directories


class TreeResponse(BaseModel):
    """Lazy-loaded directory listing — immediate children only."""
    library_id: int
    library_name: str
    rel_path: str  # the directory that was listed ("" = root)
    nodes: list[TreeNode]


def _list_dir_sync(root: Path, rel: str) -> list[dict]:
    """Synchronously list immediate children of root/rel.

    Returns a list of dicts with name, rel_path, is_dir, size.
    Skips hidden files/dirs and symbolic links (security).
    """
    target = root if not rel else root / rel
    if not target.is_dir():
        return []

    items: list[dict] = []
    try:
        for entry in sorted(os.scandir(str(target)), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.name.startswith("."):
                continue
            # Skip symlink entries (security: prevent symlink attacks)
            if entry.is_symlink():
                continue

            child_rel = entry.name if not rel else f"{rel}{os.sep}{entry.name}"
            if entry.is_dir():
                try:
                    stat = entry.stat()
                except (OSError, PermissionError):
                    stat = None
                items.append({
                    "name": entry.name,
                    "rel_path": child_rel,
                    "is_dir": True,
                    "size": None,
                    "modified_at": stat.st_mtime if stat else None,
                })
            else:
                ext = Path(entry.name).suffix.lower()
                if ext not in VIDEO_EXTENSIONS:
                    continue
                try:
                    stat = entry.stat()
                    items.append({
                        "name": entry.name,
                        "rel_path": child_rel,
                        "is_dir": False,
                        "size": stat.st_size,
                        "modified_at": stat.st_mtime,
                    })
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError):
        return []

    return items


@router.get("/{library_id}/tree", response_model=TreeResponse)
async def get_library_tree(
    library_id: int,
    path: str = Query("", description="Subdirectory relative to library root (empty = root)"),
    db: AsyncSession = Depends(get_db),
):
    """List immediate children of a directory within the library.

    Returns directories first (sorted alphabetically), then video files.
    Non-video files are excluded. Each file node includes media_id and
    scrape status if the file has been imported as a Media record.

    Security: path is resolved relative to the library root_path and
    validated to prevent directory traversal outside the library.
    """
    lib = await _get_library_or_404(db, library_id)

    try:
        root = validate_root_path(lib.root_path)
    except ValueError:
        raise HTTPException(status_code=500, detail="Library root_path is invalid")

    # Resolve the requested subdirectory and ensure it's within root
    rel = path.strip().strip("/\\")
    if rel:
        target = (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            raise HTTPException(status_code=400, detail="Path is outside library root")
        if not target.is_dir():
            raise HTTPException(status_code=404, detail="Directory not found")
    else:
        target = root

    # List directory contents synchronously in a thread (os.scandir is sync I/O)
    import asyncio
    raw_items = await asyncio.to_thread(_list_dir_sync, root, rel)

    if not raw_items:
        return TreeResponse(
            library_id=library_id,
            library_name=lib.name,
            rel_path=rel,
            nodes=[],
        )

    # Build full paths for file lookups
    file_paths = {}
    for item in raw_items:
        if not item["is_dir"]:
            full = str(target / item["name"])
            file_paths[full] = item

    # Batch query: find Media records matching these file paths
    media_map: dict[str, dict] = {}
    if file_paths:
        result = await db.execute(
            select(
                Media.id, Media.file_path, Media.poster_path, Media.scrape_data
            ).where(
                Media.library_id == library_id,
                Media.file_path.in_(list(file_paths.keys())),
            )
        )
        for row in result.fetchall():
            media_map[row[1]] = {
                "id": row[0],
                "has_poster": bool(row[2]),
                "is_scraped": bool(row[3]),
            }

    # Build response nodes
    nodes: list[TreeNode] = []
    for item in raw_items:
        if item["is_dir"]:
            # Count immediate children for display (lazy: just count, don't recurse)
            dir_path = target / item["name"]
            try:
                child_count = await asyncio.to_thread(
                    lambda: sum(
                        1 for e in os.scandir(str(dir_path))
                        if not e.name.startswith(".") and not e.is_symlink()
                    )
                )
            except (OSError, PermissionError):
                child_count = 0
            nodes.append(TreeNode(
                name=item["name"],
                rel_path=item["rel_path"],
                node_type="directory",
                modified_at=item.get("modified_at"),
                child_count=child_count,
            ))
        else:
            full = str(target / item["name"])
            info = media_map.get(full, {})
            nodes.append(TreeNode(
                name=item["name"],
                rel_path=item["rel_path"],
                node_type="file",
                size=item["size"],
                modified_at=item.get("modified_at"),
                media_id=info.get("id"),
                is_scraped=info.get("is_scraped", False),
                has_poster=info.get("has_poster", False),
            ))

    return TreeResponse(
        library_id=library_id,
        library_name=lib.name,
        rel_path=rel,
        nodes=nodes,
    )


# ---------------------------------------------------------------------------
# Directory management — create / rename / delete folders on disk
# ---------------------------------------------------------------------------

# Windows reserved names that cannot be used as directory names
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3",
                     "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
                     "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6",
                     "LPT7", "LPT8", "LPT9"}
_ILLEGAL_DIR_CHARS = set('<>:"/\\|?*')


def _validate_dirname(name: str) -> str:
    """Validate a directory name — similar to filename but also blocks
    hidden names (starting with '.') and Windows reserved names."""
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="目录名不能为空")
    name = name.strip()
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status_code=400, detail="目录名不能包含路径分隔符")
    bad = set(name) & _ILLEGAL_DIR_CHARS
    if bad:
        raise HTTPException(
            status_code=400,
            detail=f"目录名包含非法字符: {' '.join(sorted(bad))}",
        )
    if name.startswith("."):
        raise HTTPException(status_code=400, detail="目录名不能以点号开头")
    if name.upper() in _WINDOWS_RESERVED:
        raise HTTPException(status_code=400, detail=f"'{name}' 是系统保留名")
    return name


def _resolve_and_validate_dir(root: Path, rel: str) -> Path:
    """Resolve a relative path within the library root and validate it.

    Returns the resolved absolute path.
    Raises HTTPException if the path is outside root or doesn't exist.
    """
    rel = rel.strip().strip("/\\")
    if rel:
        target = (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            raise HTTPException(status_code=400, detail="路径超出了库的范围")
        return target
    return root


class CreateDirRequest(BaseModel):
    parent_path: str = ""  # relative to library root, "" = root
    dir_name: str


class RenameDirRequest(BaseModel):
    old_rel_path: str  # relative to library root
    new_name: str


class DeleteDirRequest(BaseModel):
    rel_path: str  # relative to library root
    recursive: bool = False  # if True, delete all contents


@router.post("/{library_id}/directories", status_code=201)
async def create_directory(
    library_id: int,
    payload: CreateDirRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new directory within the library.

    Security:
    - parent_path is validated to be within the library root
    - dir_name is validated (no traversal, no illegal chars, no reserved names)
    - The resulting path must not already exist
    """
    lib = await _get_library_or_404(db, library_id)

    try:
        root = validate_root_path(lib.root_path)
    except ValueError:
        raise HTTPException(status_code=500, detail="Library root_path is invalid")

    parent = _resolve_and_validate_dir(root, payload.parent_path)
    if not parent.is_dir():
        raise HTTPException(status_code=404, detail="父目录不存在")

    dir_name = _validate_dirname(payload.dir_name)
    new_dir = parent / dir_name

    if new_dir.exists():
        raise HTTPException(status_code=409, detail=f"目录已存在: {dir_name}")

    def _mkdir():
        new_dir.mkdir(parents=False, exist_ok=False)

    try:
        await asyncio.to_thread(_mkdir)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"创建目录失败: {exc}")

    logger.info("Created directory '%s' in library %s", new_dir, lib.name)
    return {
        "status": "created",
        "library_id": library_id,
        "rel_path": str(new_dir.relative_to(root)),
        "name": dir_name,
    }


@router.put("/{library_id}/directories/rename")
async def rename_directory(
    library_id: int,
    payload: RenameDirRequest,
    db: AsyncSession = Depends(get_db),
):
    """Rename a directory on disk and update all affected Media records.

    Updates the file_path of every Media record whose file is inside the
    renamed directory (prefix replacement).
    """
    lib = await _get_library_or_404(db, library_id)

    try:
        root = validate_root_path(lib.root_path)
    except ValueError:
        raise HTTPException(status_code=500, detail="Library root_path is invalid")

    old_dir = _resolve_and_validate_dir(root, payload.old_rel_path)
    if not old_dir.is_dir():
        raise HTTPException(status_code=404, detail="要重命名的目录不存在")
    if old_dir == root:
        raise HTTPException(status_code=400, detail="不能重命名库的根目录")

    new_name = _validate_dirname(payload.new_name)
    new_dir = old_dir.parent / new_name

    if new_dir == old_dir:
        raise HTTPException(status_code=400, detail="新目录名与旧名相同")
    if new_dir.exists():
        raise HTTPException(status_code=409, detail=f"目标目录已存在: {new_name}")

    old_str = str(old_dir)
    new_str = str(new_dir)

    # Rename the physical directory
    def _rename():
        old_dir.rename(new_dir)

    try:
        await asyncio.to_thread(_rename)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"重命名目录失败: {exc}")

    # Batch-update all Media records under the old directory prefix
    from sqlalchemy import update as sa_update
    # SQLite doesn't support REPLACE() across all versions reliably for path
    # prefix replacement, so we fetch + update row by row (only affected rows).
    # S4 fix: a bare LIKE f"{old_str}%" would also match sibling directories
    # (e.g. "Show2" when renaming "Show") — filter precisely in Python by
    # requiring the path to equal the dir or start with a separator.
    result = await db.execute(
        select(Media.id, Media.file_path).where(
            Media.library_id == library_id,
            Media.file_path.like(f"{old_str}%"),
        )
    )
    affected = [
        (mid, fp)
        for mid, fp in result.fetchall()
        if fp == old_str
        or fp.startswith(old_str + os.sep)
        or fp.startswith(old_str + "/")
    ]
    updated = 0
    for media_id, file_path in affected:
        new_path = new_str + file_path[len(old_str):]
        # uq_media_library_file: another row (incl. soft-deleted) may already
        # occupy the target path — skip that row instead of aborting the
        # whole rename with an IntegrityError (disk is already renamed).
        dup = await db.execute(
            select(Media.id).where(
                Media.file_path == new_path,
                Media.id != media_id,
            )
        )
        if dup.scalar_one_or_none() is not None:
            logger.warning(
                "Skip path update for media %d: target already taken (%s)",
                media_id, new_path,
            )
            continue
        await db.execute(
            sa_update(Media).where(Media.id == media_id).values(file_path=new_path)
        )
        updated += 1
    if updated:
        await db.commit()

    logger.info(
        "Renamed directory '%s' -> '%s' in library %s (%d media paths updated)",
        old_dir.name, new_name, lib.name, updated,
    )
    return {
        "status": "renamed",
        "library_id": library_id,
        "old_rel_path": payload.old_rel_path,
        "new_rel_path": str(new_dir.relative_to(root)),
        "updated_media_count": updated,
    }


@router.delete("/{library_id}/directories")
async def delete_directory(
    library_id: int,
    rel_path: str = Query(..., description="Directory relative to library root"),
    recursive: bool = Query(False, description="If true, delete all contents recursively"),
    db: AsyncSession = Depends(get_db),
):
    """Delete a directory on disk.

    If recursive=False and the directory is not empty, returns 400.
    If recursive=True, deletes all files inside and marks affected Media
    records as file_missing (soft-delete approach — records are kept).

    Security:
    - Cannot delete the library root
    - Path must be within library root
    """
    lib = await _get_library_or_404(db, library_id)

    try:
        root = validate_root_path(lib.root_path)
    except ValueError:
        raise HTTPException(status_code=500, detail="Library root_path is invalid")

    target = _resolve_and_validate_dir(root, rel_path)
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="目录不存在")
    if target == root:
        raise HTTPException(status_code=400, detail="不能删除库的根目录")

    # Check if directory has contents
    def _check_empty():
        try:
            entries = list(os.scandir(str(target)))
            return len(entries) == 0
        except OSError:
            return False

    is_empty = await asyncio.to_thread(_check_empty)

    if not is_empty and not recursive:
        raise HTTPException(
            status_code=400,
            detail="目录非空，请勾选'递归删除'以删除目录及其所有内容",
        )

    # If recursive, mark all affected Media records as file_missing first
    affected_count = 0
    target_str = str(target)
    if not is_empty:
        from sqlalchemy import update as sa_update
        from datetime import datetime, timezone as dt_tz
        result = await db.execute(
            select(Media.id, Media.file_path).where(
                Media.library_id == library_id,
                Media.file_path.like(f"{target_str}%"),
                Media.is_deleted == False,  # noqa: E712
            )
        )
        # S4 fix: LIKE "%" prefix would match sibling dirs (e.g. "Show2");
        # require the path to equal the dir or start with a separator.
        affected_ids = [
            mid
            for mid, fp in result.fetchall()
            if fp == target_str
            or fp.startswith(target_str + os.sep)
            or fp.startswith(target_str + "/")
        ]
        if affected_ids:
            now_naive = datetime.now(dt_tz.utc).replace(tzinfo=None)
            await db.execute(
                sa_update(Media).where(Media.id.in_(affected_ids)).values(
                    file_missing=True,
                    missing_detected_at=now_naive,
                    media_type=MediaType.OFFLINE,
                )
            )
            await db.commit()
            affected_count = len(affected_ids)

    # Delete the physical directory
    import shutil

    def _rmtree():
        if is_empty:
            target.rmdir()
        else:
            shutil.rmtree(str(target))

    try:
        await asyncio.to_thread(_rmtree)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"删除目录失败: {exc}")

    logger.info(
        "Deleted directory '%s' in library %s (recursive=%s, %d media marked missing)",
        target.name, lib.name, recursive, affected_count,
    )
    return {
        "status": "deleted",
        "library_id": library_id,
        "rel_path": rel_path,
        "affected_media_count": affected_count,
    }


class MoveFileRequest(BaseModel):
    target_library_id: int
    target_dir: str = ""  # relative to target library root, "" = root


@router.put("/{library_id}/files/move")
async def move_files_to_directory(
    library_id: int,
    payload: MoveFileRequest,
    media_ids: str = Query(..., description="Comma-separated media IDs"),
    db: AsyncSession = Depends(get_db),
):
    """Move multiple files to a target directory within a library.

    Physically moves the files on disk and updates their file_path in the DB.
    Supports cross-library moves (source library_id → target_library_id).

    Security:
    - Target directory must be within the target library root
    - Source files must exist on disk and not be file_missing
    - File name conflicts are resolved by appending a suffix
    """
    lib = await _get_library_or_404(db, library_id)
    target_lib = await _get_library_or_404(db, payload.target_library_id)

    try:
        target_root = validate_root_path(target_lib.root_path)
    except ValueError:
        raise HTTPException(status_code=500, detail="Target library root_path is invalid")

    target_dir = _resolve_and_validate_dir(target_root, payload.target_dir)
    if not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="目标目录不存在")

    # Parse media IDs
    try:
        ids = [int(x.strip()) for x in media_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid media_ids format")
    if not ids:
        raise HTTPException(status_code=400, detail="No media IDs provided")

    # Load Media records
    result = await db.execute(
        select(Media).where(
            Media.id.in_(ids),
            Media.is_deleted == False,  # noqa: E712
        )
    )
    media_list = result.scalars().all()

    if not media_list:
        raise HTTPException(status_code=404, detail="No valid media records found")

    import shutil

    moved = 0
    skipped = 0
    errors: list[dict] = []

    for media in media_list:
        if not media.file_path or media.file_missing:
            skipped += 1
            errors.append({"media_id": media.id, "reason": "文件丢失或无本地路径"})
            continue

        src = Path(media.file_path)
        if not src.is_file():
            skipped += 1
            errors.append({"media_id": media.id, "reason": "源文件在磁盘上未找到"})
            continue

        dest = target_dir / src.name
        # Resolve name conflicts: append " (1)", " (2)", etc.
        # Also check the DB (incl. soft-deleted rows) for uq_media_library_file
        # conflicts — a recycle-bin record may occupy the path with no file on
        # disk. Resolve BEFORE the physical move so disk and DB stay in sync.
        stem, ext = dest.stem, dest.suffix
        counter = 0
        while True:
            disk_hit = dest.exists()
            db_result = await db.execute(
                select(Media.id).where(
                    Media.library_id == payload.target_library_id,
                    Media.file_path == str(dest),
                    Media.id != media.id,
                )
            )
            if not disk_hit and db_result.scalar_one_or_none() is None:
                break
            counter += 1
            dest = target_dir / f"{stem} ({counter}){ext}"

        # Physically move the file
        def _move(src=src, dest=dest):
            shutil.move(str(src), str(dest))

        try:
            await asyncio.to_thread(_move)
        except (OSError, shutil.Error) as exc:
            skipped += 1
            errors.append({"media_id": media.id, "reason": str(exc)})
            continue

        # Update DB record
        media.file_path = str(dest)
        media.file_name = dest.name
        if payload.target_library_id != library_id:
            media.library_id = payload.target_library_id
        moved += 1

    if moved:
        await db.commit()

    logger.info(
        "Moved %d/%d files to '%s' in library %s (%d skipped)",
        moved, len(ids), target_dir, target_lib.name, skipped,
    )
    return {
        "status": "completed",
        "moved": moved,
        "skipped": skipped,
        "errors": errors,
    }


class ImportFilesRequest(BaseModel):
    source_paths: list[str]  # absolute paths picked by the user
    target_dir: str = ""  # relative to library root, "" = root
    action: str = "copy"  # "copy" (button import) | "move" (drag-drop)


@router.post("/{library_id}/files/import")
async def import_files(
    library_id: int,
    payload: ImportFilesRequest,
    db: AsyncSession = Depends(get_db),
):
    """Copy or move external files into a library directory and trigger a scan.

    Server-side transfer (replaces the old frontend copyFile flow) so that:
    - name conflicts are resolved the same way as move-files: " (1)", " (2)"…
      checking both disk and DB (incl. soft-deleted recycle-bin rows);
    - non-video files are rejected before touching the disk;
    - scan is enqueued once for the whole batch (deduped against an
      already pending/running scan task).

    action="copy" keeps the source (import button); action="move" removes the
    source after transfer (drag-drop). Files already at the exact target
    location are skipped without side effects.

    Returns a per-file result list so the UI can show what was renamed.
    """
    import shutil

    if payload.action not in ("copy", "move"):
        raise HTTPException(status_code=400, detail="action 仅支持 copy 或 move")
    if not payload.source_paths:
        raise HTTPException(status_code=400, detail="未选择任何文件")

    lib = await _get_library_or_404(db, library_id)
    try:
        root = validate_root_path(lib.root_path)
    except ValueError:
        raise HTTPException(status_code=500, detail="库根目录无效")
    target_dir = _resolve_and_validate_dir(root, payload.target_dir)
    if not target_dir.is_dir():
        raise HTTPException(status_code=404, detail="目标目录不存在")

    imported = 0
    skipped = 0
    results: list[dict] = []

    for src_str in payload.source_paths:
        src = Path(src_str)
        if not src.is_file():
            skipped += 1
            results.append({"source": src_str, "status": "skipped", "reason": "源文件不存在"})
            continue
        if src.suffix.lower() not in VIDEO_EXTENSIONS:
            skipped += 1
            results.append({"source": src_str, "status": "skipped", "reason": "不支持的视频格式"})
            continue
        if src.resolve() == (target_dir / src.name).resolve():
            skipped += 1
            results.append({"source": src_str, "status": "skipped", "reason": "文件已在目标目录"})
            continue

        dest = target_dir / src.name
        stem, ext = dest.stem, dest.suffix
        counter = 0
        while True:
            disk_hit = dest.exists()
            db_result = await db.execute(
                select(Media.id).where(
                    Media.library_id == library_id,
                    Media.file_path == str(dest),
                )
            )
            if not disk_hit and db_result.scalar_one_or_none() is None:
                break
            counter += 1
            dest = target_dir / f"{stem} ({counter}){ext}"

        def _transfer(src=src, dest=dest):
            if payload.action == "move":
                shutil.move(str(src), str(dest))
            else:
                shutil.copy2(str(src), str(dest))

        try:
            await asyncio.to_thread(_transfer)
        except OSError as exc:
            skipped += 1
            results.append({"source": src_str, "status": "skipped", "reason": str(exc)})
            continue

        renamed = dest.name != src.name
        imported += 1
        results.append(
            {"source": src_str, "status": "imported", "imported_as": dest.name, "renamed": renamed}
        )

    if imported:
        await db.commit()
        scan_info = await _enqueue_scan_if_idle(library_id, lib.name)
    else:
        scan_info = {"status": "not_needed"}

    logger.info(
        "Imported %d/%d files into '%s' in library %s (%d skipped)",
        imported, len(payload.source_paths), target_dir, lib.name, skipped,
    )
    return {
        "status": "completed",
        "imported": imported,
        "skipped": skipped,
        "results": results,
        "scan": scan_info,
    }
