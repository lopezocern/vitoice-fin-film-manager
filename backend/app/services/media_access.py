"""Single-source gate for resolving a Media row by id.

**Why this module exists**

Before 2026-09-02 the soft-delete / restricted-content checks lived inline in
``api/media.py::_get_media_or_404`` only. Nine other endpoints resolved media
with a bare ``db.get(Media, media_id)``, so a user who turned *off* "show
restricted content" could still read subtitles, segments, tags, media URLs and
series data of a restricted library by calling those endpoints directly — and
soft-deleted (recycle bin) rows were reachable too.

**Rule**

Every endpoint that resolves a media by id MUST go through
:func:`get_accessible_media`. Do not call ``db.get(Media, ...)`` in an API
module. Endpoints that legitimately operate on deleted rows (recycle bin)
pass ``allow_deleted=True``.
"""
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.media import Media
from app.services.restricted import get_restricted_library_ids

__all__ = ["get_accessible_media"]


async def get_accessible_media(
    db: AsyncSession,
    media_id: int,
    *,
    allow_deleted: bool = False,
) -> Media:
    """Load a media row, enforcing soft-delete and restricted-content gates.

    Raises:
        HTTPException(404): not found, soft-deleted (unless ``allow_deleted``),
            or belongs to a library hidden by the restricted-content switch.

    Note the 404 (not 403) for restricted rows on purpose: returning 403 would
    confirm the row exists, leaking the very fact the switch is meant to hide.
    """
    media = await db.get(Media, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")

    if not allow_deleted and media.is_deleted:
        raise HTTPException(status_code=404, detail="Media not found")

    restricted_ids = await get_restricted_library_ids(db)
    if restricted_ids and media.library_id in restricted_ids:
        raise HTTPException(status_code=404, detail="Media not found")

    return media
