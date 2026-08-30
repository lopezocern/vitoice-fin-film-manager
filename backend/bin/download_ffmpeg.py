"""Download full ffmpeg + ffprobe binaries into backend/bin/.

The binaries are git-ignored (too large for the repo). Run this script
once after cloning, or during CI/build packaging.

Usage:
    python backend/bin/download_ffmpeg.py

On success, ffmpeg(.exe) and ffprobe(.exe) will be placed in backend/bin/.
The app's _get_ffmpeg() will find them automatically.
"""
from __future__ import annotations

import os
import platform
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

# Target directory (backend/bin/, next to this script)
BIN_DIR = Path(__file__).resolve().parent

# --- Platform-specific download URLs -----------------------------------------

# Windows: Gyan's full build (includes all encoders: aac, libx264, nvenc, etc.)
# macOS:   evermeet.cx static builds
# Linux:   BtbN GPL static builds
_URLS = {
    ("Windows", "64bit"): {
        "url": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-full.7z",
        # Fallback: BtbN GPL build (zip, easier to extract)
        "fallback": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
        "format": "zip",  # using BtbN fallback for easier extraction
    },
}


def _get_ffmpeg_url() -> tuple[str, str]:
    """Return (url, format) for the current platform."""
    system = platform.system()
    machine = platform.machine()

    if system == "Windows" and "64" in machine:
        # Use BtbN GPL build (zip format, easy to extract, always latest)
        return (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
            "zip",
        )
    elif system == "Darwin":
        return ("https://evermeet.cx/ffmpeg/getrelease/zip", "zip")
    elif system == "Linux":
        arch = "linux64" if "64" in machine else "linux32"
        return (
            f"https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-{arch}-gpl.tar.xz",
            "tarxz",
        )
    else:
        raise RuntimeError(f"Unsupported platform: {system} {machine}")


def _extract_binaries(archive_path: Path, fmt: str) -> None:
    """Extract ffmpeg and ffprobe from the downloaded archive."""
    if fmt == "zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            # Find ffmpeg and ffprobe in the archive
            for name in zf.namelist():
                lower = name.lower()
                if lower.endswith("ffmpeg.exe") or lower.endswith("ffmpeg"):
                    _extract_file(zf, name, BIN_DIR / "ffmpeg")
                elif lower.endswith("ffprobe.exe") or lower.endswith("ffprobe"):
                    _extract_file(zf, name, BIN_DIR / "ffprobe")
    elif fmt == "tarxz":
        import tarfile

        with tarfile.open(archive_path, "r:xz") as tf:
            for member in tf.getmembers():
                lower = member.name.lower()
                if lower.endswith("ffmpeg") or lower.endswith("ffprobe"):
                    member.name = os.path.basename(member.name)
                    tf.extract(member, BIN_DIR)
    else:
        raise ValueError(f"Unknown format: {fmt}")


def _extract_file(zf: zipfile.ZipFile, src: str, dest: Path) -> None:
    """Extract a single file from a zip archive."""
    with zf.open(src) as src_f, open(dest, "wb") as dst_f:
        shutil.copyfileobj(src_f, dst_f)
    # Make executable on Unix
    if platform.system() != "Windows":
        dest.chmod(0o755)
    print(f"  Extracted: {dest.name} ({dest.stat().st_size // (1024*1024)} MB)")


def main() -> int:
    # Check if already present
    ffmpeg = BIN_DIR / ("ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
    ffprobe = BIN_DIR / ("ffprobe.exe" if platform.system() == "Windows" else "ffprobe")

    if ffmpeg.is_file() and ffprobe.is_file():
        print(f"ffmpeg and ffprobe already exist in {BIN_DIR}")
        return 0

    url, fmt = _get_ffmpeg_url()
    print(f"Downloading ffmpeg from: {url}")
    print(f"Format: {fmt}")
    print(f"Target: {BIN_DIR}")
    print()

    # Download to temp file
    with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as tmp:
        print("Downloading...", end=" ", flush=True)
        try:
            urllib.request.urlretrieve(url, tmp.name)
            print("Done!")
        except Exception as e:
            print(f"Failed: {e}")
            return 1

        # Extract
        print("Extracting binaries...")
        try:
            _extract_binaries(Path(tmp.name), fmt)
        except Exception as e:
            print(f"Extraction failed: {e}")
            return 1
        finally:
            os.unlink(tmp.name)

    # Verify
    if ffmpeg.is_file():
        print(f"\nSuccess! ffmpeg: {ffmpeg}")
    else:
        print(f"\nWarning: ffmpeg not found at {ffmpeg}")

    if ffprobe.is_file():
        print(f"Success! ffprobe: {ffprobe}")
    else:
        # ffprobe may not be in all builds; fall back to imageio-ffmpeg's ffprobe
        print(f"Warning: ffprobe not found at {ffprobe} (will use system PATH)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
