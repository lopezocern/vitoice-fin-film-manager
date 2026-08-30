"""Duplicate detection — group media by content hash / filename / file size.

Read-only grouping endpoint; the actual cleanup reuses the existing
batch delete (soft-delete to recycle bin) flow on the frontend.

Note: file_hash is a 64KB-prefix blake2b hash written by the metadata task.
Groups found by hash are strong duplicate candidates (same 64KB prefix at
the same file size is nearly impossible for different encodes); name/size
groups are weaker hints and are labeled as such in the UI.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.library import MediaLibrary
from app.models.media import Media
from app.services.restricted import get_restricted_library_ids

logger = logging.getLogger("vitoice.api.duplicates")
router = APIRouter(prefix="/duplicates", tags=["duplicates"])

# size 模式下忽略小于该阈值的文件（小文件同大小太常见，误报多）
_MIN_SIZE_BYTES = 10 * 1024 * 1024

_MODE_ATTR = {"hash": "file_hash", "name": "file_name", "size": "file_size"}


def _base_conds(mode: str, restricted: set[int]) -> list:
    """Common WHERE conditions for both the key-grouping and item queries."""
    conds = [
        Media.is_deleted == False,  # noqa: E712
        Media.file_missing == False,  # noqa: E712
    ]
    if mode == "hash":
        conds += [Media.file_hash.is_not(None), Media.file_hash != ""]
    elif mode == "size":
        conds += [Media.file_size.is_not(None), Media.file_size >= _MIN_SIZE_BYTES]
    if restricted:
        conds.append(Media.library_id.not_in(restricted))
    return conds


@router.get("")
async def find_duplicates(
    mode: str = Query("hash", description="hash | name | size"),
    limit_groups: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Find duplicate media groups.

    Returns {"mode", "groups": [{key, items: [...]}], "truncated"}.
    Items are sorted by size desc within a group so the UI can default to
    keeping the largest copy.
    """
    if mode not in _MODE_ATTR:
        raise HTTPException(status_code=400, detail="mode 仅支持 hash | name | size")

    restricted = await get_restricted_library_ids(db)
    conds = _base_conds(mode, restricted)
    key_col = getattr(Media, _MODE_ATTR[mode])

    keys_q = (
        select(key_col)
        .where(*conds)
        .group_by(key_col)
        .having(func.count(Media.id) > 1)
        .limit(limit_groups)
    )
    keys = [k for k in (await db.execute(keys_q)).scalars().all() if k is not None]

    if not keys:
        return {"mode": mode, "groups": [], "truncated": False}

    rows = (
        await db.execute(
            select(Media, MediaLibrary.name)
            .join(MediaLibrary, Media.library_id == MediaLibrary.id, isouter=True)
            .where(*conds, key_col.in_(keys))
            .order_by(Media.file_size.desc().nullslast(), Media.created_at.asc())
        )
    ).all()

    groups: dict[str, list[dict]] = {}
    for m, lib_name in rows:
        groups.setdefault(str(getattr(m, _MODE_ATTR[mode])), []).append(
            {
                "id": m.id,
                "title": m.title,
                "file_name": m.file_name,
                "file_path": m.file_path,
                "library_id": m.library_id,
                "library_name": lib_name,
                "file_size": m.file_size,
                "duration": m.duration,
                "has_poster": bool(m.poster_path),
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
        )

    result_groups = [
        {"key": k, "items": items} for k, items in groups.items() if len(items) > 1
    ]
    result_groups.sort(key=lambda g: len(g["items"]), reverse=True)

    return {
        "mode": mode,
        "groups": result_groups[:limit_groups],
        "truncated": len(keys) >= limit_groups,
    }
