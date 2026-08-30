"""Shared helpers for content restriction filtering.

Provides a single entry point ``get_restricted_library_ids()`` that checks
the ``show_restricted`` setting and returns the set of library IDs that
should be excluded from queries when the user has not enabled restricted
content display.

Usage in API routes:

    from app.services.restricted import get_restricted_library_ids

    restricted_ids = await get_restricted_library_ids(db)
    if restricted_ids:
        query = query.where(~Media.library_id.in_(restricted_ids))
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library import MediaLibrary
from app.models.setting import Setting


async def should_hide_restricted(db: AsyncSession) -> bool:
    """Return True when restricted content should be hidden.

    Convenience wrapper for endpoints that filter by non-library dimensions
    (e.g. tag types) and only need a boolean answer.
    """
    result = await db.execute(
        select(Setting.value).where(Setting.key == "show_restricted")
    )
    raw = result.scalar()
    show_restricted = (raw or "").strip().lower() in ("true", "1", "yes")
    return not show_restricted


async def should_mask_restricted(db: AsyncSession) -> bool:
    """Return True when restricted content should be visually masked.

    When ``show_restricted`` is ON and ``mask_restricted`` is also ON,
    restricted library posters and video frames are blurred with an
    overlay. This gives the user control over whether to see restricted
    content thumbnails or keep them masked.
    """
    result = await db.execute(
        select(Setting.value).where(Setting.key == "mask_restricted")
    )
    raw = result.scalar()
    return (raw or "").strip().lower() in ("true", "1", "yes")


async def get_restricted_library_ids(db: AsyncSession) -> set[int]:
    """Return library IDs that should be excluded from queries.

    Returns an empty set when the user has enabled ``show_restricted``,
    meaning no filtering is needed and callers can skip the extra WHERE clause.
    """
    # Check the show_restricted setting (defaults to false / not present)
    result = await db.execute(
        select(Setting.value).where(Setting.key == "show_restricted")
    )
    raw = result.scalar()
    show_restricted = (raw or "").strip().lower() in ("true", "1", "yes")

    if show_restricted:
        return set()

    # Get all restricted library IDs
    result = await db.execute(
        select(MediaLibrary.id).where(MediaLibrary.is_restricted == True)  # noqa: E712
    )
    return set(result.scalars().all())
