"""Missing-file reconciliation — merge shadow duplicates.

Root cause scenario: user copies files to a new location while the app is
closed, scans the library (a fresh record is created at the new path while
the original still exists), then deletes the original. The old record is
then marked file_missing while an identical live record exists at the new
path — a "shadow duplicate" pair.

This service:
1. Finds such pairs (same library + file_name, matching file_size).
2. Merges the missing record's user data into the live record
   (progress max / watched+favorite OR / rating+poster+series fallback /
   tag union / segments+subtitles+media_urls re-point).
3. Soft-deletes the stale missing record into the recycle bin.

Used by the manage-page "找回缺失文件" flow (preview + execute API) and by
the scanner's Phase 6 guard that prevents new shadow duplicates.
"""
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.media import Media, MediaUrl, VideoTag
from app.models.segment import Segment
from app.models.subtitle import Subtitle


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def find_pairs(
    db: AsyncSession,
    library_ids: list[int] | None = None,
) -> list[dict]:
    """Match file_missing records against live same-name records.

    A pair requires: same library, same file_name, and (when both sizes are
    known) equal file_size. A missing record with unknown size may still
    match on name alone — flagged as ``size_matched: False``.

    Returns preview dicts, one per missing record:
    ``{missing_id, live_id, file_name, file_size, size_matched,
       missing_path, live_path, missing_progress, live_progress,
       live_watched, missing_tags, live_tags}``
    """
    m_rows = (await db.execute(
        select(Media).where(
            Media.file_missing.is_(True),
            Media.is_deleted.is_(False),
            Media.file_path.is_not(None),
        )
    )).scalars().all()

    l_rows = (await db.execute(
        select(Media).where(
            Media.is_deleted.is_(False),
            Media.file_missing.is_(False),
        )
    )).scalars().all()

    # Index live records by (library_id, file_name)
    live_index: dict[tuple[int, str], list[Media]] = {}
    for lm in l_rows:
        live_index.setdefault((lm.library_id, lm.file_name), []).append(lm)

    pairs: list[dict] = []
    for m in m_rows:
        if library_ids is not None and m.library_id not in library_ids:
            continue
        candidates = live_index.get((m.library_id, m.file_name), [])
        if not candidates:
            continue
        # Size-preferred: exact size match wins; unknown missing size falls
        # back to name-only; mismatched size is NOT a pair.
        size_matches = [c for c in candidates if c.file_size is not None
                        and m.file_size is not None
                        and c.file_size == m.file_size]
        name_only = [c for c in candidates if m.file_size is None]
        chosen = (size_matches or name_only)
        if not chosen:
            continue
        live = chosen[0]
        size_matched = bool(size_matches)

        m_tag_ids = (await db.execute(
            select(VideoTag.tag_id).where(VideoTag.media_id == m.id)
        )).scalars().all()
        l_tag_ids = (await db.execute(
            select(VideoTag.tag_id).where(VideoTag.media_id == live.id)
        )).scalars().all()

        pairs.append({
            "missing_id": m.id,
            "live_id": live.id,
            "file_name": m.file_name,
            "file_size": m.file_size,
            "size_matched": size_matched,
            "missing_path": m.file_path,
            "live_path": live.file_path,
            "missing_progress": m.playback_position or 0.0,
            "live_progress": live.playback_position or 0.0,
            "live_watched": live.is_watched,
            "missing_tag_count": len(m_tag_ids),
            "live_tag_count": len(l_tag_ids),
        })
    return pairs


async def reconcile_pair(
    db: AsyncSession, missing_id: int, live_id: int,
    *, pending_missing: bool = False,
) -> None:
    """Merge the missing record (M) into the live record (L), soft-delete M.

    Re-derives both records from their ids (does not trust caller-loaded
    objects), so it is safe to call with only ids from a preview payload.

    ``pending_missing=True`` allows merging a record whose ``file_missing``
    flag has not been committed yet (scanner Phase 6 guard runs before the
    missing-marking update).
    """
    m = (await db.execute(
        select(Media).where(Media.id == missing_id)
    )).scalar_one_or_none()
    l = (await db.execute(
        select(Media).where(Media.id == live_id)
    )).scalar_one_or_none()
    if m is None or l is None:
        raise ValueError(f"reconcile: missing record {missing_id} or live record {live_id} not found")
    if m.id == l.id:
        raise ValueError("reconcile: cannot merge a record into itself")
    if m.is_deleted or l.is_deleted:
        raise ValueError(
            f"reconcile: media {m.id}/{l.id} is already deleted"
        )
    if not pending_missing and not m.file_missing:
        raise ValueError(
            f"reconcile: media {m.id} is not marked missing — refusing merge"
        )

    # --- User data: take the better of the two -----------------------------
    l.playback_position = max(l.playback_position or 0.0, m.playback_position or 0.0)
    l.is_watched = bool(l.is_watched) or bool(m.is_watched)
    l.is_favorite = bool(l.is_favorite) or bool(m.is_favorite)
    if m.last_played_at and (not l.last_played_at or m.last_played_at > l.last_played_at):
        l.last_played_at = m.last_played_at
    if l.rating is None and m.rating is not None:
        l.rating = m.rating

    # --- Fallbacks: fresh live record lacks scraped/manual metadata ---------
    for field in ("description", "year", "release_date", "season_number",
                  "episode_number", "scrape_data", "thumbnail_path",
                  "poster_path", "poster_source", "series_id", "series_title",
                  "duration", "width", "height", "codec"):
        if getattr(l, field) is None:
            setattr(l, field, getattr(m, field))

    # --- Tag union (respect uq media_id+tag_id) ------------------------------
    l_tag_ids = set((await db.execute(
        select(VideoTag.tag_id).where(VideoTag.media_id == l.id)
    )).scalars().all())
    m_tag_ids = (await db.execute(
        select(VideoTag.tag_id).where(VideoTag.media_id == m.id)
    )).scalars().all()
    for tid in m_tag_ids:
        if tid not in l_tag_ids:
            db.add(VideoTag(media_id=l.id, tag_id=tid))
            l_tag_ids.add(tid)
    # Drop M's own tag rows — union above already preserved them on L
    from sqlalchemy import delete
    await db.execute(delete(VideoTag).where(VideoTag.media_id == m.id))

    # --- Re-point child rows to the live record ------------------------------
    for model in (Segment, Subtitle, MediaUrl):
        await db.execute(
            update(model).where(model.media_id == m.id).values(media_id=l.id)
        )

    # --- Soft-delete the stale missing record (recycle bin) ------------------
    m.is_deleted = True
    m.deleted_at = _now()
    m.file_missing = False
    m.missing_detected_at = None

    await db.flush()


async def reconcile_pairs(
    db: AsyncSession, pairs: list[dict]
) -> dict:
    """Execute a batch of preview pairs. Returns a result summary."""
    merged: list[int] = []
    failed: list[dict] = []
    for p in pairs:
        try:
            await reconcile_pair(db, int(p["missing_id"]), int(p["live_id"]))
            merged.append(int(p["missing_id"]))
        except (ValueError, KeyError) as exc:
            failed.append({"missing_id": p.get("missing_id"), "error": str(exc)})
    await db.commit()
    return {"merged": merged, "failed": failed, "merged_count": len(merged)}
