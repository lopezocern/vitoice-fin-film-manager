"""Media URL CRUD routes — resource link management for media items.

Extracted from media.py for API physical isolation.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.proxy import get_proxy_url
from app.services.ssrf import validate_http_url
from app.services.restricted import get_restricted_library_ids
from app.services.media_access import get_accessible_media
from app.services.assets import cleanup_asset_files
from app.models.enums import MediaType, UrlRole
from app.models.media import Media, MediaUrl
from app.schemas.media import MediaUrlCreate, MediaUrlResponse, MediaUrlUpdate

router = APIRouter(prefix="/media", tags=["media-urls"])


async def _get_media_or_404(db: AsyncSession, media_id: int) -> Media:
    """Delegate to the shared access gate (see app.services.media_access).

    This module previously carried its own copy of the soft-delete +
    restricted checks. Duplicated gates drift apart, so all media resolution
    now goes through one implementation.
    """
    return await get_accessible_media(db, media_id)


@router.post("/{media_id}/urls", response_model=MediaUrlResponse, status_code=201)
async def create_media_url(
    media_id: int,
    payload: MediaUrlCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a resource URL to a media item.

    Adding a ``source`` URL upgrades a single-channel media to BOTH:
      - LOCAL   (local file present) → BOTH (e.g. attaching adult aggregator
        links to local files so the player can switch sources)
      - OFFLINE (local file missing) stays OFFLINE — it regains BOTH via the
        watcher recovery path once the file is back
    NETWORK / BOTH keep their type. ``reference`` URLs never change the type.
    """
    media = await _get_media_or_404(db, media_id)
    url = MediaUrl(media_id=media_id, **payload.model_dump())
    db.add(url)
    await db.flush()
    await db.refresh(url)

    # Upgrade to BOTH when a source URL is added to a single-channel local media
    if (
        url.url_role == UrlRole.SOURCE
        and media.media_type in (MediaType.LOCAL, MediaType.OFFLINE)
    ):
        # LOCAL/OFFLINE -> BOTH via shared helper. Note: OFFLINE stays
        # OFFLINE while the local file is missing (regains BOTH through
        # watcher recovery when the file returns).
        from app.services.media_type import promote_media_type_for_source
        promote_media_type_for_source(media)
        await db.flush()

    return url


@router.put("/{media_id}/urls/{url_id}", response_model=MediaUrlResponse)
async def update_media_url(
    media_id: int,
    url_id: int,
    payload: MediaUrlUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a resource URL."""
    result = await db.execute(
        select(MediaUrl).where(MediaUrl.id == url_id, MediaUrl.media_id == media_id)
    )
    url = result.scalar_one_or_none()
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(url, field, value)
    await db.flush()
    await db.refresh(url)
    return url


@router.delete("/{media_id}/urls/{url_id}", status_code=204)
async def delete_media_url(
    media_id: int,
    url_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a resource URL, downgrading the media type when the last
    playable SOURCE source is removed.

    Only SOURCE deletions can downgrade (reference links never change type).
    After deleting: if no playable SOURCE remains:
      - NETWORK → the record has nothing playable left → deleted entirely
      - BOTH with the local file present → back to LOCAL
      - BOTH with the local file lost → back to OFFLINE
      - OFFLINE → stays OFFLINE (record kept for future recovery)
    The delete-and-downgrade happens in the same session/transaction.
    """
    media = await _get_media_or_404(db, media_id)

    result = await db.execute(
        select(MediaUrl).where(MediaUrl.id == url_id, MediaUrl.media_id == media_id)
    )
    url = result.scalar_one_or_none()
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")
    is_source = url.url_role == UrlRole.SOURCE
    await db.delete(url)
    await db.flush()

    if not is_source:
        return

    # Recompute type via the shared helper (same semantics as before:
    # NETWORK with nothing left -> record deleted; BOTH -> OFFLINE/LOCAL).
    from app.services.media_type import demote_media_type_after_source_removal
    await demote_media_type_after_source_removal(media, db)

    await db.flush()


@router.post("/{media_id}/urls/{url_id}/check")
async def check_url_validity(
    media_id: int,
    url_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Check if a URL is still valid (not expired).

    Performs an HTTP HEAD request to verify the URL is reachable.
    Updates is_expired field based on the result.
    """
    import httpx

    result = await db.execute(
        select(MediaUrl).where(MediaUrl.id == url_id, MediaUrl.media_id == media_id)
    )
    url = result.scalar_one_or_none()
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")

    try:
        validate_http_url(url.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0, connect=10.0),
            follow_redirects=True,
            proxy=await get_proxy_url(),
        ) as client:
            resp = await client.head(url.url)
            is_expired = resp.status_code >= 400

        url.is_expired = is_expired
        await db.flush()

        return {
            "url_id": url.id,
            "is_expired": is_expired,
            "status_code": resp.status_code,
            "checked": True,
        }
    except httpx.RequestError:
        url.is_expired = True
        await db.flush()
        return {
            "url_id": url.id,
            "is_expired": True,
            "status_code": None,
            "checked": False,
            "error": "Network request failed",
        }


@router.put("/{media_id}/urls/{url_id}/progress")
async def update_url_progress(
    media_id: int,
    url_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    """Update playback progress for a specific URL (cross-source sync)."""
    from datetime import datetime, timezone

    result = await db.execute(
        select(MediaUrl).where(MediaUrl.id == url_id, MediaUrl.media_id == media_id)
    )
    url = result.scalar_one_or_none()
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")

    played_progress = payload.get("played_progress", 0.0)
    try:
        url.played_progress = float(played_progress)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="played_progress 必须是数字")
    url.last_visited_at = datetime.now(timezone.utc).replace(tzinfo=None)

    # Mirror the local progress endpoint (media.py): keep the Media row's
    # watch state in sync so network media also appear in "continue watching"
    # and最近播放, which sort by last_played_at.
    # Gate: progress must not be writable (nor existence inferable) for
    # restricted / soft-deleted media.
    media = await get_accessible_media(db, media_id)
    media.playback_position = url.played_progress
    media.last_played_at = url.last_visited_at
    if media.duration and url.played_progress >= media.duration * 0.95:
        media.is_watched = True
    await db.flush()

    return {
        "url_id": url.id,
        "played_progress": url.played_progress,
        "last_visited_at": url.last_visited_at.isoformat() if url.last_visited_at else None,
    }


@router.get("/{media_id}/urls/{url_id}/progress")
async def get_url_progress(
    media_id: int,
    url_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get playback progress for a specific URL."""
    result = await db.execute(
        select(MediaUrl).where(MediaUrl.id == url_id, MediaUrl.media_id == media_id)
    )
    url = result.scalar_one_or_none()
    if not url:
        raise HTTPException(status_code=404, detail="URL not found")

    return {
        "url_id": url.id,
        "played_progress": url.played_progress,
        "last_visited_at": url.last_visited_at.isoformat() if url.last_visited_at else None,
    }
