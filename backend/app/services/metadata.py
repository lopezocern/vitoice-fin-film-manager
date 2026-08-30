"""Metadata extraction using ffprobe subprocess.

Extracts duration, resolution, codec, fps, bitrate from video files.
Uses asyncio.to_thread + subprocess.run for Windows compatibility
(SelectorEventLoop does not support create_subprocess_exec).
"""
import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.database import async_session
from app.models.media import Media
from app.models.subtitle import Subtitle
from app.models.enums import SubtitleSourceType
from app.services.ffmpeg_utils import get_ffprobe

logger = logging.getLogger("vitoice.metadata")

# Max retries for database-locked errors during batch processing
_DB_RETRY_COUNT = 3
_DB_RETRY_DELAY = 0.5  # seconds


def _run_ffprobe_sync(file_path: str) -> dict | None:
    """Run ffprobe synchronously (called via asyncio.to_thread)."""
    cmd = [
        get_ffprobe(),
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        "--",
        file_path,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout.decode("utf-8"))
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


async def run_ffprobe(file_path: str) -> dict | None:
    """Run ffprobe and return parsed metadata (Windows-safe)."""
    return await asyncio.to_thread(_run_ffprobe_sync, file_path)


async def extract_metadata(media_id: int) -> bool:
    """Extract metadata for a single media file.

    Returns True on success.
    Retries on database-locked errors (common during bulk import).
    """
    async with async_session() as session:
        media = await session.get(Media, media_id)
        if not media or not media.file_path:
            return False

        if not os.path.exists(media.file_path):
            return False

    # Run ffprobe and file hash outside the DB session (I/O-bound, no lock)
    data = await run_ffprobe(media.file_path)
    if not data:
        return False

    # Parse metadata (in-memory, no DB needed)
    fmt = data.get("format", {})
    duration = float(fmt.get("duration", 0)) or None
    bitrate = int(fmt.get("bit_rate", 0)) or None
    width = height = codec = fps = None
    streams = data.get("streams", [])
    for stream in streams:
        if stream.get("codec_type") == "video":
            width = stream.get("width")
            height = stream.get("height")
            codec = stream.get("codec_name")
            fps_str = stream.get("r_frame_rate", "0/1")
            try:
                num, den = fps_str.split("/")
                fps = float(num) / float(den) if float(den) != 0 else None
            except (ValueError, ZeroDivisionError):
                fps = None
            break

    file_hash = await asyncio.to_thread(compute_file_hash_sync, media.file_path)

    # Write to DB with retry on lock
    for attempt in range(_DB_RETRY_COUNT):
        try:
            async with async_session() as session:
                media = await session.get(Media, media_id)
                if not media:
                    return False
                media.duration = duration
                media.bitrate = bitrate
                media.width = width
                media.height = height
                media.codec = codec
                media.fps = fps
                media.file_hash = file_hash
                await session.commit()
            break
        except OperationalError as e:
            if "locked" in str(e) and attempt < _DB_RETRY_COUNT - 1:
                logger.warning(
                    "DB locked on metadata update for media %s (attempt %d/%d)",
                    media_id, attempt + 1, _DB_RETRY_COUNT,
                )
                await asyncio.sleep(_DB_RETRY_DELAY * (attempt + 1))
            else:
                raise

    # Detect/register subtitles (embedded streams + sidecar files) so the
    # player can display them. Best-effort: never blocks metadata extraction.
    # Reuse the ffprobe data already fetched above to avoid a second subprocess
    # call. extract_subtitles opens its own session and is idempotent (skips
    # already-registered subtitles), so re-runs are safe.
    try:
        await extract_subtitles(media_id, ffprobe_data=data)
    except Exception:  # noqa: BLE001 — subtitle detection must not break metadata
        logger.warning("Subtitle extraction failed for media %s", media_id, exc_info=True)

    return True


def compute_file_hash_sync(file_path: str, chunk_size: int = 65536) -> str:
    """Sync file hash (64KB prefix). Uses blake2b (non-crypto, fast)."""
    import hashlib

    hasher = hashlib.blake2b(digest_size=16)
    try:
        with open(file_path, "rb") as f:
            hasher.update(f.read(chunk_size))
    except (OSError, PermissionError):
        return ""
    return hasher.hexdigest()


async def extract_subtitles(media_id: int, ffprobe_data: dict | None = None) -> int:
    """Detect and register embedded + sidecar subtitles for a media file.

    Embedded subtitle streams are detected via ffprobe. External sidecar
    files (e.g. ``movie.srt`` next to ``movie.mkv``) are detected by
    scanning the file's directory for matching stems.

    If ``ffprobe_data`` is provided (from a prior ``run_ffprobe`` call in
    the same pipeline), it is reused instead of calling ffprobe again.
    This avoids a redundant subprocess invocation during metadata extraction.

    Idempotent: existing subtitle records (matched by ``stream_index`` for
    embedded, by ``file_path`` for external) are skipped, so re-running on
    the same media does not create duplicates. Returns the number of NEW
    subtitle records created.
    """
    async with async_session() as session:
        media = await session.get(Media, media_id)
        if not media or not media.file_path:
            return 0

        # --- Load existing subtitle records for dedup ---
        existing = await session.execute(
            select(Subtitle).where(Subtitle.media_id == media_id)
        )
        existing_subs = existing.scalars().all()
        embedded_indices = {
            s.stream_index for s in existing_subs
            if s.source_type == SubtitleSourceType.EMBEDDED
            and s.stream_index is not None
        }
        external_paths = {
            (s.file_path or "") for s in existing_subs
            if s.source_type == SubtitleSourceType.EXTERNAL
        }

        count = 0

        # --- Embedded subtitles via ffprobe (reuse if provided) ---
        data = ffprobe_data if ffprobe_data is not None else await run_ffprobe(media.file_path)
        if data:
            streams = data.get("streams", [])
            for stream in streams:
                if stream.get("codec_type") != "subtitle":
                    continue

                index = stream.get("index", 0)
                if index in embedded_indices:
                    continue  # already registered

                lang = stream.get("tags", {}).get("language", "und")
                title = stream.get("tags", {}).get("title", "")
                codec = stream.get("codec_name", "")

                # Map codec to format
                fmt_map = {"subrip": "srt", "ass": "ass", "ssa": "ssa", "webvtt": "vtt", "mov_text": "vtt"}
                file_format = fmt_map.get(codec, codec)

                sub = Subtitle(
                    media_id=media_id,
                    source_type=SubtitleSourceType.EMBEDDED,
                    language=lang,
                    title=title or f"Stream {index}",
                    stream_index=index,
                    file_format=file_format,
                )
                session.add(sub)
                count += 1

        # --- External sidecar subtitles (same stem, subtitle extension) ---
        # Matches "movie.srt" for "movie.mkv", and language-suffixed names
        # like "movie.zh.srt" / "movie.en.vtt" (language parsed from suffix).
        video_path = Path(media.file_path)
        stem = video_path.stem
        sidecar_exts = {".srt", ".vtt", ".ass", ".ssa"}
        try:
            for sibling in video_path.parent.iterdir():
                if sibling.is_dir() or sibling.is_symlink():
                    continue
                if sibling.suffix.lower() not in sidecar_exts:
                    continue
                sib_stem = sibling.stem
                if sib_stem != stem and not sib_stem.startswith(stem + "."):
                    continue
                sp = str(sibling)
                if sp in external_paths:
                    continue  # already registered
                # Derive language from a ".zh"/".en" suffix if present
                lang = "und"
                if sib_stem != stem:
                    suffix = sib_stem[len(stem) + 1:].lower()
                    if suffix:
                        lang = suffix
                fmt = sibling.suffix.lower().lstrip(".")
                sub = Subtitle(
                    media_id=media_id,
                    source_type=SubtitleSourceType.EXTERNAL,
                    language=lang,
                    title=sibling.name,
                    file_path=sp,
                    file_format=fmt,
                )
                session.add(sub)
                count += 1
        except (OSError, PermissionError):
            pass

        if count:
            await session.commit()

    return count


async def extract_metadata_batch(library_id: int, task_id: int | None = None) -> int:
    """Extract metadata for all media in a library that lacks it.

    Called by TaskManager as a task worker.
    """
    from app.tasks.manager import task_manager

    processed = 0

    async with async_session() as session:
        result = await session.execute(
            select(Media.id, Media.file_name).where(
                Media.library_id == library_id,
                Media.duration.is_(None),
                Media.file_path.is_not(None),
                Media.is_deleted == False,  # noqa: E712
                Media.file_missing == False,  # noqa: E712
            )
        )
        items = result.fetchall()

    total = len(items)
    # Update progress every N files to reduce DB writes (and lock contention)
    # during bulk imports. Always update on the last item.
    _PROGRESS_INTERVAL = 5
    for i, (media_id, file_name) in enumerate(items):
        try:
            success = await extract_metadata(media_id)
            if success:
                processed += 1
        except OperationalError:
            logger.warning(
                "Metadata extraction failed for media %s after retries, skipping",
                media_id,
            )

        if task_id and ((i + 1) % _PROGRESS_INTERVAL == 0 or i + 1 == total):
            try:
                await task_manager.update_progress(
                    task_id, current=i + 1, total=total, subtitle=file_name,
                )
            except OperationalError:
                # Progress update is non-critical; don't let it abort the batch
                pass

    return processed
