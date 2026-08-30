"""Subtitle routes."""
import asyncio
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.media import Media
from app.models.subtitle import Subtitle
from app.schemas.subtitle import SubtitleCreate, SubtitleResponse, SubtitleUpdate

router = APIRouter(tags=["subtitles"])


def _validate_path(file_path: str) -> Path | None:
    """Validate a file path for safe access.

    Rejects paths with ``..`` components (path traversal) and symlinks.
    Returns the resolved Path, or None if the path is unsafe.
    """
    raw = Path(file_path)
    if ".." in raw.parts:
        return None
    try:
        resolved = raw.resolve()
    except (OSError, RuntimeError):
        return None
    if resolved.is_symlink():
        return None
    return resolved


def _validate_subtitle_path(file_path: str, media_file_path: str | None) -> Path | None:
    """Validate a subtitle file path against the owning media's directory.

    S2 security fix: an external subtitle file must live inside the media
    file's directory (or a subdirectory of it). Arbitrary absolute paths
    are rejected so the subtitle-content endpoint cannot read unrelated
    files. Returns the resolved Path, or None if unsafe.
    """
    sub_path = _validate_path(file_path)
    if sub_path is None:
        return None
    if not media_file_path:
        return None  # media has no local file — refuse arbitrary file paths
    try:
        media_dir = Path(media_file_path).resolve().parent
    except (OSError, RuntimeError):
        return None
    if sub_path == media_dir or media_dir in sub_path.parents:
        return sub_path
    return None


@router.get("/media/{media_id}/subtitles", response_model=list[SubtitleResponse])
async def list_subtitles(media_id: int, db: AsyncSession = Depends(get_db)):
    """List all subtitles for a media item."""
    media = await db.get(Media, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    result = await db.execute(
        select(Subtitle).where(Subtitle.media_id == media_id)
    )
    return result.scalars().all()


@router.post("/media/{media_id}/subtitles", response_model=SubtitleResponse, status_code=201)
async def create_subtitle(
    media_id: int,
    payload: SubtitleCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a subtitle to a media item."""
    media = await db.get(Media, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    data = payload.model_dump()

    # S2 security fix: external subtitle files must live in the media's
    # directory — reject arbitrary paths that would allow reading any file.
    if data.get("file_path"):
        if _validate_subtitle_path(data["file_path"], media.file_path) is None:
            raise HTTPException(
                status_code=400,
                detail="字幕文件路径必须位于媒体文件所在目录内",
            )

    data["media_id"] = media_id
    subtitle = Subtitle(**data)
    db.add(subtitle)
    await db.flush()
    await db.refresh(subtitle)
    return subtitle


@router.put("/subtitles/{subtitle_id}", response_model=SubtitleResponse)
async def update_subtitle(
    subtitle_id: int,
    payload: SubtitleUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a subtitle."""
    subtitle = await db.get(Subtitle, subtitle_id)
    if not subtitle:
        raise HTTPException(status_code=404, detail="Subtitle not found")
    update_data = payload.model_dump(exclude_unset=True)

    # S2 security fix: same path restriction as create.
    if update_data.get("file_path"):
        media = await db.get(Media, subtitle.media_id)
        if _validate_subtitle_path(
            update_data["file_path"], media.file_path if media else None
        ) is None:
            raise HTTPException(
                status_code=400,
                detail="字幕文件路径必须位于媒体文件所在目录内",
            )

    for field, value in update_data.items():
        setattr(subtitle, field, value)
    await db.flush()
    await db.refresh(subtitle)
    return subtitle


@router.delete("/subtitles/{subtitle_id}", status_code=204)
async def delete_subtitle(subtitle_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a subtitle."""
    subtitle = await db.get(Subtitle, subtitle_id)
    if not subtitle:
        raise HTTPException(status_code=404, detail="Subtitle not found")
    await db.delete(subtitle)
    await db.flush()


@router.get("/media/{media_id}/subtitles/{subtitle_id}/content")
async def get_subtitle_content(
    media_id: int, subtitle_id: int, db: AsyncSession = Depends(get_db)
):
    """Return the text content of a subtitle.

    For file-backed subtitles the file is read directly. For embedded
    subtitles, ffmpeg is used to extract the stream to WebVTT on the fly.
    """
    subtitle = await db.get(Subtitle, subtitle_id)
    if not subtitle or subtitle.media_id != media_id:
        raise HTTPException(status_code=404, detail="Subtitle not found")

    # Load owning media once — needed for both path validation and the
    # embedded-subtitle extraction branch below.
    media = await db.get(Media, media_id)

    # File-backed subtitle (with path traversal protection)
    if subtitle.file_path:
        # S2: enforce the same directory restriction on read — legacy rows
        # with out-of-media paths are treated as unavailable.
        sub_path = _validate_subtitle_path(subtitle.file_path, media.file_path if media else None)
        if sub_path and sub_path.is_file():
            try:
                with open(sub_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(sub_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            return {
                "content": content,
                "format": subtitle.file_format,
                "language": subtitle.language,
                "source": "file",
            }

    # Embedded subtitle — extract via ffmpeg if available
    media_path: Path | None = None
    if media and media.file_path:
        media_path = _validate_path(media.file_path)
    if (
        subtitle.stream_index is not None
        and media_path
        and media_path.is_file()
    ):
        def _extract_subtitle_sync() -> bytes:
            """Extract subtitle via ffmpeg synchronously (called via to_thread).

            Uses imageio-ffmpeg's bundled full build when available, matching
            the thumbnail service pattern for Windows compatibility.
            """
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            except ImportError:
                ffmpeg_exe = settings.ffmpeg_path
            result = subprocess.run(
                [
                    ffmpeg_exe,
                    "-i", str(media_path),
                    "-map", f"0:s:{subtitle.stream_index}",
                    "-f", "webvtt", "pipe:1",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
            return result.stdout or b""

        try:
            out = await asyncio.to_thread(_extract_subtitle_sync)
            if not out:
                raise HTTPException(
                    status_code=501,
                    detail="嵌入式字幕提取失败（ffmpeg 不可用或格式不支持）",
                )
            return {
                "content": out.decode("utf-8", errors="replace"),
                "format": "webvtt",
                "language": subtitle.language,
                "source": "extracted",
            }
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001 — ffmpeg missing or unsupported stream
            raise HTTPException(
                status_code=501,
                detail="嵌入式字幕提取失败（ffmpeg 不可用或格式不支持）",
            )

    raise HTTPException(
        status_code=404,
        detail="字幕内容不可用（无字幕文件且无法提取嵌入流）",
    )
