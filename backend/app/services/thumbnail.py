"""Thumbnail generation using ffmpeg subprocess.

Uses asyncio.to_thread + subprocess.run for Windows compatibility
(SelectorEventLoop does not support create_subprocess_exec).
"""
import asyncio
import logging
import os
import subprocess
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.database import async_session
from app.models.media import Media
from app.services.ffmpeg_utils import get_ffmpeg, get_ffprobe

logger = logging.getLogger("vitoice.thumbnail")

# Settings-table keys that override the pydantic config defaults at runtime.
# (The Settings page saves these; historically they were dead keys.)
_OVERRIDE_KEYS = {
    "thumbnail_size": "thumbnail_size",
    "thumbnail_quality": "thumbnail_quality",
    "thumbnail_offset": "thumbnail_time_offset",
    "thumbnail_smart_frame": "thumbnail_smart_frame",
}

# Candidate time points (as fraction of duration) for smart frame selection.
_SMART_FRAME_FRACTIONS = (0.02, 0.10, 0.25, 0.50)


async def _load_thumbnail_settings() -> dict:
    """Load runtime thumbnail settings from the settings table (best-effort).

    Falls back to the config defaults when the table is unavailable or the
    key is missing, so thumbnail generation never breaks on a fresh DB.
    """
    from app.models.setting import Setting

    out = {
        "size": settings.thumbnail_size,
        "quality": settings.thumbnail_quality,
        "offset": settings.thumbnail_time_offset,
        "smart_frame": getattr(settings, "thumbnail_smart_frame", True),
    }
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Setting.key, Setting.value).where(Setting.key.in_(_OVERRIDE_KEYS))
            )
            for key, value in result.fetchall():
                if value is None or value == "":
                    continue
                try:
                    if key == "thumbnail_size":
                        out["size"] = int(value)
                    elif key == "thumbnail_quality":
                        out["quality"] = int(value)
                    elif key == "thumbnail_offset":
                        out["offset"] = float(value)
                    elif key == "thumbnail_smart_frame":
                        out["smart_frame"] = value.lower() in ("1", "true", "yes", "on")
                except (TypeError, ValueError):
                    continue
    except Exception:  # noqa: BLE001 — best-effort, never fail thumbnailing
        pass
    return out


def _is_blank_frame(image_path: str, threshold: float = 6.0) -> bool:
    """Return True if an extracted frame is blank/near-uniform (black screen).

    Computes the standard deviation of the grayscale pixels — a black/white/
    solid-color frame has near-zero variance, while real content has texture.
    """
    try:
        from PIL import Image
        import numpy as np

        with Image.open(image_path) as img:
            gray = img.convert("L")
            # Downscale before computing to keep it fast
            small = gray.resize((64, 36), Image.Resampling.BILINEAR)
            arr = np.asarray(small, dtype=np.float32)
            return float(arr.std()) < threshold
    except Exception:  # noqa: BLE001 — if we cannot judge, treat as usable
        return False


def _generate_thumbnail_sync(
    file_path: str,
    output_path: str,
    offset: float,
    thumb_size: int,
    thumb_quality: int,
    smart_frame: bool = False,
    duration_hint: float | None = None,
) -> bool:
    """Generate thumbnail synchronously (called via asyncio.to_thread).

    Uses imageio-ffmpeg's bundled full ffmpeg for JPEG output support.
    Falls back to pipe + Pillow if needed.

    With ``smart_frame`` enabled, several candidate time points are sampled and
    the first non-blank frame is used, skipping black/credits screens.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe = get_ffmpeg()

    def _run_one(off: float, dest: str) -> bool:
        cmd = [
            ffmpeg_exe,
            "-ss", str(off),
            "-i", file_path,
            "-frames:v", "1",
            "-vf", f"scale={thumb_size}:-2",  # -2 ensures even dimensions
            "-q:v", str(max(2, min(31, 31 - thumb_quality * 29 // 100))),
            "-y",
            dest,
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, timeout=30, check=False
            )
            return result.returncode == 0 and os.path.exists(dest)
        except (subprocess.SubprocessError, OSError):
            return False

    try:
        # Smart frame: try candidates in order, keep the first non-blank one.
        if smart_frame:
            candidates: list[float] = []
            if duration_hint and duration_hint > 5:
                candidates = [duration_hint * f for f in _SMART_FRAME_FRACTIONS]
            # Always include the user-configured offset as a candidate
            if not any(abs(c - offset) < 0.01 for c in candidates):
                candidates.append(offset)
            for off in candidates:
                if _run_one(off, output_path):
                    if not _is_blank_frame(output_path):
                        return True
                    # Blank — remove and try the next candidate
                    try:
                        os.remove(output_path)
                    except OSError:
                        pass

        # Default path (or all candidates were blank): single frame at offset
        if _run_one(offset, output_path):
            return True

        # Fallback: rawvideo pipe + Pillow (if direct JPEG output fails)
        import json as _json
        probe_cmd = [
            get_ffprobe(),
            "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            "--",
            file_path,
        ]
        probe_result = subprocess.run(
            probe_cmd, capture_output=True, timeout=10, check=False
        )
        if probe_result.returncode != 0:
            return False
        probe_data = _json.loads(probe_result.stdout.decode("utf-8"))
        streams = probe_data.get("streams", [])
        if not streams:
            return False
        src_w = int(streams[0].get("width", 0))
        src_h = int(streams[0].get("height", 0))
        if src_w <= 0 or src_h <= 0:
            return False

        out_w = thumb_size if thumb_size % 2 == 0 else thumb_size + 1
        out_h = int(src_h * thumb_size / src_w)
        out_h = out_h if out_h % 2 == 0 else out_h + 1

        pipe_cmd = [
            ffmpeg_exe,
            "-ss", str(offset),
            "-i", file_path,
            "-frames:v", "1",
            "-vf", f"scale={out_w}:{out_h}",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "pipe:1",
        ]
        pipe_result = subprocess.run(
            pipe_cmd,
            capture_output=True,
            timeout=30,
            check=False,
        )
        if pipe_result.returncode != 0 or not pipe_result.stdout:
            return False

        from PIL import Image
        # Use context manager to ensure Image is closed
        with Image.frombytes("RGB", (out_w, out_h), pipe_result.stdout) as img:
            # Pillow quality is 1-95 (higher = better); map our 0-100 to 10-95
            pil_quality = max(10, min(95, int(thumb_quality * 0.85 + 10)))
            img.save(output_path, "JPEG", quality=pil_quality)
        return os.path.exists(output_path)
    except (subprocess.SubprocessError, OSError, ValueError, KeyError):
        # Expected failures: ffmpeg errors, file access, bad video data
        return False
    except Exception:
        logger.exception(
            "Unexpected thumbnail generation error for %s", file_path
        )
        return False

async def generate_thumbnail(
    file_path: str,
    output_path: str,
    time_offset: float | None = None,
    size: int | None = None,
    quality: int | None = None,
    duration: float | None = None,
) -> bool:
    """Generate a thumbnail from a video file (Windows-safe).

    Uses -ss before -i for fast seek (keyframe-based, near-instant for large files).
    Reads runtime thumbnail settings (size/quality/offset/smart-frame) from the
    settings table, falling back to config defaults.
    """
    rt = await _load_thumbnail_settings()
    offset = time_offset if time_offset is not None else rt["offset"]
    thumb_size = size or rt["size"]
    thumb_quality = quality or rt["quality"]
    smart_frame = rt["smart_frame"]

    return await asyncio.to_thread(
        _generate_thumbnail_sync,
        file_path,
        output_path,
        offset,
        thumb_size,
        thumb_quality,
        smart_frame,
        duration,
    )


async def generate_thumbnail_batch(
    library_id: int,
    task_id: int | None = None,
    max_concurrent: int = 4,
) -> int:
    """Generate thumbnails for all media in a library that lacks them.

    Runs multiple ffmpeg subprocesses concurrently for speed.
    Called by TaskManager as a task worker.
    """
    from app.tasks.manager import task_manager

    generated = 0

    async with async_session() as session:
        result = await session.execute(
            select(Media.id, Media.file_path).where(
                Media.library_id == library_id,
                Media.thumbnail_path.is_(None),
                Media.file_path.is_not(None),
                Media.is_deleted == False,  # noqa: E712
                Media.file_missing == False,  # noqa: E712
            )
        )
        items = result.fetchall()

    total = len(items)
    if total == 0:
        return 0

    # Process in concurrent batches
    semaphore = asyncio.Semaphore(max_concurrent)
    completed_count = 0  # Monotonic counter (no progress regression)

    async def process_one(media_id: int, file_path: str, index: int):
        nonlocal generated, completed_count
        async with semaphore:
            if not os.path.exists(file_path):
                return

            # Output path: thumbnails/{media_id}.jpg
            output_path = str(settings.thumbnail_dir / f"{media_id}.jpg")

            success = await generate_thumbnail(file_path, output_path)
            if success:
                for attempt in range(3):
                    try:
                        async with async_session() as session:
                            media = await session.get(Media, media_id)
                            if media:
                                media.thumbnail_path = output_path
                                await session.commit()
                        generated += 1
                        break
                    except OperationalError as e:
                        if "locked" in str(e) and attempt < 2:
                            await asyncio.sleep(0.5 * (attempt + 1))
                        else:
                            logger.warning(
                                "DB locked on thumbnail update for media %s, skipping",
                                media_id,
                            )

            completed_count += 1  # Monotonic (no progress regression)
            if task_id and (completed_count % 5 == 0 or completed_count == total):
                try:
                    await task_manager.update_progress(
                        task_id, current=completed_count, total=total,
                        subtitle=os.path.basename(file_path),
                    )
                except OperationalError:
                    pass

    # Run all tasks concurrently (semaphore limits actual parallelism)
    tasks = [
        process_one(item[0], item[1], i)
        for i, item in enumerate(items)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Log any unexpected errors from gather
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.warning("Thumbnail task %d failed: %s", i, r)

    return generated
