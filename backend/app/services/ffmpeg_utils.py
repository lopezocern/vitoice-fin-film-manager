"""Unified ffmpeg/ffprobe path resolution.

Priority (highest first):
1. backend/bin/ffmpeg(.exe) — bundled with the app (full build, has AAC)
2. imageio-ffmpeg package  — pip dependency, always available as fallback
3. System PATH             — user-installed system ffmpeg

All services (media streaming, thumbnail generation, metadata extraction)
should use these functions instead of各自硬编码路径。
"""
import sys
from pathlib import Path

# backend/ directory when running from source: this file lives at
# backend/app/services/ffmpeg_utils.py, so three levels up is backend/.
#
# Under PyInstaller (onedir) the bundle is unpacked into `_internal/` and the
# bundled ffmpeg lands there too (see vitoice-backend.spec: `('bin', 'bin')`).
# A frozen module's `__file__` is a synthetic path managed by PyInstaller's
# importer and is NOT a reliable anchor, so resolve against `sys._MEIPASS`
# explicitly instead of hoping `parent.parent.parent` happens to line up.
if getattr(sys, "frozen", False):  # pragma: no cover - only true in the packaged app
    _BACKEND_DIR = Path(sys._MEIPASS)
else:
    _BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

_FFMPEG_PATH: str | None = None
_FFPROBE_PATH: str | None = None


def get_ffmpeg() -> str:
    """Get ffmpeg executable path.

    Priority:
    1. backend/bin/ffmpeg(.exe) — bundled with the app
    2. imageio-ffmpeg package  — pip dependency, always available as fallback
    3. PATH                    — user-installed system ffmpeg
    """
    global _FFMPEG_PATH
    if _FFMPEG_PATH is None:
        exe_suffix = ".exe" if sys.platform == "win32" else ""
        # 1. Project-bundled ffmpeg (ships with the app)
        bundled = _BACKEND_DIR / "bin" / f"ffmpeg{exe_suffix}"
        if bundled.is_file():
            _FFMPEG_PATH = str(bundled)
        else:
            # 2. imageio-ffmpeg (pip dependency, full build with AAC encoder)
            try:
                import imageio_ffmpeg
                _FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
            except ImportError:
                # 3. System PATH
                import shutil
                _FFMPEG_PATH = shutil.which("ffmpeg") or "ffmpeg"
    return _FFMPEG_PATH


def get_ffprobe() -> str:
    """Get ffprobe executable path (same priority order as ffmpeg).

    Note: imageio-ffmpeg only ships ffmpeg, not ffprobe.
    So ffprobe falls back to system PATH when not bundled.
    """
    global _FFPROBE_PATH
    if _FFPROBE_PATH is None:
        exe_suffix = ".exe" if sys.platform == "win32" else ""
        # 1. Project-bundled ffprobe
        bundled = _BACKEND_DIR / "bin" / f"ffprobe{exe_suffix}"
        if bundled.is_file():
            _FFPROBE_PATH = str(bundled)
        else:
            # 2. System PATH
            import shutil
            _FFPROBE_PATH = shutil.which("ffprobe") or "ffprobe"
    return _FFPROBE_PATH
