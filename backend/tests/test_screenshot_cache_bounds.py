"""Bounded preview-screenshot cache — GET /media/{id}/screenshot.

The endpoint used to persist one JPEG per hovered second under
thumbnails/screenshots/{media_id}/ forever (unbounded growth across scrub
sessions). New contract:
  - disk keeps at most _SCREENSHOT_DISK_MAX frames per media dir, oldest
    pruned right after a brand-new frame is written;
  - the in-process LRU holds at most _SCREENSHOT_LRU_MAX byte entries.

Only the pure helpers are unit-tested here — ffmpeg frame extraction needs a
real video file and is intentionally out of scope for this file.
"""
import os
from pathlib import Path

import pytest

from app.api import media as media_api


def _touch(d: Path, name: str, mtime: float) -> None:
    f = d / name
    f.write_bytes(b"jpeg" * 10)
    os.utime(f, (mtime, mtime))


def test_disk_cap_prunes_oldest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media_api, "_SCREENSHOT_DISK_MAX", 5)
    d = tmp_path / "media42"
    d.mkdir(parents=True)

    # 8 frames with strictly increasing mtimes (frame 0 = oldest)
    base = 2_000_000.0
    for i in range(8):
        _touch(d, f"{i}.jpg", base + i)

    media_api._prune_screenshot_dir(d)

    remaining = sorted(int(p.stem) for p in d.glob("*.jpg"))
    assert remaining == [3, 4, 5, 6, 7]  # newest 5 kept, oldest 3 unlinked


def test_disk_cap_exact_limit_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media_api, "_SCREENSHOT_DISK_MAX", 3)
    d = tmp_path / "media42"
    d.mkdir(parents=True)
    for i in range(3):
        _touch(d, f"{i}.jpg", 1_000_000.0 + i)

    media_api._prune_screenshot_dir(d)

    assert sorted(int(p.stem) for p in d.glob("*.jpg")) == [0, 1, 2]


def test_disk_cap_ignores_missing_dir(tmp_path: Path) -> None:
    # Never raises, never creates the directory
    missing = tmp_path / "does-not-exist"
    media_api._prune_screenshot_dir(missing)
    assert not missing.exists()


def test_cache_bounds_constants_are_sane() -> None:
    assert media_api._SCREENSHOT_DISK_MAX >= 100
    assert media_api._SCREENSHOT_LRU_MAX >= 16
    # Memory cap must stay small enough to be a hot-cache, not a shadow of disk
    assert media_api._SCREENSHOT_LRU_MAX < media_api._SCREENSHOT_DISK_MAX
