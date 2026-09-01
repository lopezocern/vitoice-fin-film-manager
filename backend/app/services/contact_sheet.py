"""Contact sheet (缩略图集) — 16 frames composed into a 4×4 grid image.

手动触发功能（详情页按钮 / 管理页批量）：
- 每格 480×270（cover 填充裁切），4×4 合成后恰好 1920×1080，无留边
- 抽帧时刻 = duration * (i + 0.5) / 16（每格取该区间中点，避免正片黑场头尾）
- 输出 {thumbnail_dir}/contact_sheets/{media_id}.jpg（可再生缓存，不入 DB）
"""
import asyncio
import logging
import os
import subprocess
from pathlib import Path

from app.config import settings
from app.services.ffmpeg_utils import get_ffmpeg

logger = logging.getLogger("vitoice.contact_sheet")

GRID_COLS = 4
GRID_ROWS = 4
CELL_W = 480
CELL_H = 270
OUTPUT_W = GRID_COLS * CELL_W  # 1920
OUTPUT_H = GRID_ROWS * CELL_H  # 1080
JPEG_QUALITY = 85


def contact_sheet_path(media_id: int) -> Path:
    return settings.thumbnail_dir / "contact_sheets" / f"{media_id}.jpg"


def _extract_and_compose_sync(
    file_path: str,
    output_path: str,
    duration: float,
    cell_w: int = CELL_W,
    cell_h: int = CELL_H,
) -> bool:
    """Extract 16 frames with ffmpeg fast-seek and compose the grid (sync)."""
    ffmpeg_exe = get_ffmpeg()
    out_dir = Path(output_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    total = GRID_COLS * GRID_ROWS
    tmp_paths: list[Path] = []

    try:
        # 1) Extract frames — each into its own temp file so a failed seek
        #    just leaves one black cell instead of corrupting the whole sheet.
        for i in range(total):
            offset = duration * (i + 0.5) / total
            tmp = out_dir / f".cs_{os.getpid()}_{Path(output_path).stem}_{i}.jpg"
            tmp_paths.append(tmp)
            if tmp.is_file():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            cmd = [
                ffmpeg_exe,
                "-ss", f"{max(0.0, offset):.3f}",
                "-i", file_path,
                "-frames:v", "1",
                "-vf",
                (
                    f"scale={cell_w}:{cell_h}:force_original_aspect_ratio=increase,"
                    f"crop={cell_w}:{cell_h}"
                ),
                "-q:v", "3",
                "-y",
                str(tmp),
            ]
            try:
                subprocess.run(cmd, capture_output=True, timeout=30, check=False)
            except (subprocess.SubprocessError, OSError):
                pass  # leave a black cell

        # 2) Compose the 4×4 grid with PIL (black background fills gaps).
        from PIL import Image

        sheet = Image.new("RGB", (OUTPUT_W, OUTPUT_H), (0, 0, 0))
        for i, tmp in enumerate(tmp_paths):
            if not tmp.is_file():
                continue
            try:
                with Image.open(tmp) as frame:
                    frame = frame.convert("RGB")
                    if frame.size != (cell_w, cell_h):
                        frame = frame.resize((cell_w, cell_h))
                    col = i % GRID_COLS
                    row = i // GRID_COLS
                    sheet.paste(frame, (col * cell_w, row * cell_h))
            except Exception:  # noqa: BLE001 — bad frame file: keep black cell
                logger.debug("Bad contact-sheet frame %s", tmp, exc_info=True)

        sheet.save(output_path, "JPEG", quality=JPEG_QUALITY)
    except Exception:
        logger.exception("Contact sheet compose failed for %s", file_path)
        return False
    finally:
        for tmp in tmp_paths:
            try:
                if tmp.is_file():
                    tmp.unlink()
            except OSError:
                pass

    return os.path.exists(output_path)


async def generate_contact_sheet(
    file_path: str,
    media_id: int,
    duration: float,
) -> bool:
    """Generate the contact sheet for one media item (Windows-safe).

    Returns True when the 1920×1080 sheet was written to disk.
    """
    if not file_path or not os.path.isfile(file_path):
        return False
    if not duration or duration <= 0:
        return False

    output_path = str(contact_sheet_path(media_id))
    return await asyncio.to_thread(
        _extract_and_compose_sync, file_path, output_path, duration
    )
