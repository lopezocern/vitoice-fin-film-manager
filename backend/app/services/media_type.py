"""Media type consistency — single source of truth for type transitions
triggered by MediaUrl SOURCE changes.

Semantic contract (mirrors DELETE /media/{id}/urls/{url_id}):
- media_type describes how the media can be played:
    LOCAL    local file only, no network source
    NETWORK  network sources only, no local file
    BOTH     local file + network sources
    OFFLINE  local file lost (file_missing), kept for recovery
- Adding the first SOURCE url:   LOCAL -> BOTH (OFFLINE stays OFFLINE while
  the local file is missing; it regains BOTH via the watcher recovery path
  once the file is back)
- Removing the last playable SOURCE url:
    NETWORK -> nothing playable left -> delete the record entirely
    BOTH    -> OFFLINE if file_missing else LOCAL
    OFFLINE -> stays OFFLINE
    LOCAL   -> cannot hold SOURCE, unchanged
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MediaType, UrlRole
from app.models.media import Media, MediaUrl
from app.services.assets import cleanup_asset_files

logger = logging.getLogger("vitoice.media_type")


async def _remaining_playable_sources(db: AsyncSession, media_id: int) -> int:
    result = await db.execute(
        select(MediaUrl.id).where(
            MediaUrl.media_id == media_id,
            MediaUrl.url_role == UrlRole.SOURCE,
            MediaUrl.is_expired == False,  # noqa: E712
        )
    )
    return len(result.fetchall())


def promote_media_type_for_source(media: Media) -> bool:
    """Call AFTER adding a SOURCE url to ``media``. Returns True if changed."""
    if media.media_type == MediaType.LOCAL:
        media.media_type = MediaType.BOTH
        return True
    # OFFLINE: the local file is missing — adding a network source doesn't
    # make it BOTH until the file is back (watcher recovery handles that).
    return False


async def demote_media_type_after_source_removal(media: Media, db: AsyncSession) -> bool:
    """Call AFTER deleting SOURCE url(s) from ``media``.

    Recomputes the type from the remaining playable sources, using the same
    semantics as the URL delete endpoint. Returns True if the record was
    deleted entirely (NETWORK with nothing left).

    NOTE: callers must flush/commit afterwards.
    """
    if media.media_type not in (MediaType.NETWORK, MediaType.BOTH):
        return False

    if await _remaining_playable_sources(db, media.id) > 0:
        return False

    if media.media_type == MediaType.NETWORK:
        # Nothing playable left — mirror the delete endpoint: drop the record.
        cleanup_asset_files(media)
        await db.delete(media)
        logger.info("Media %s removed (last NETWORK source gone)", media.id)
        return True

    # BOTH -> OFFLINE / LOCAL
    media.media_type = MediaType.OFFLINE if media.file_missing else MediaType.LOCAL
    logger.info("Media %s demoted to %s (last SOURCE gone)", media.id, media.media_type)
    return False
