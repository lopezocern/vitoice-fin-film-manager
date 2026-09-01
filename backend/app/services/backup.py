"""Automatic daily database backup (SQLite backup API — WAL-safe).

Backups live under ``settings.backup_dir`` as ``vitoice-YYYYMMDD-HHMMSS.db``.
One backup per calendar day (created lazily on the first check of the day);
older files are rotated beyond ``KEEP_COUNT``.

The stdlib ``sqlite3`` backup API copies a consistent snapshot even while
the aiosqlite engine holds the WAL — no lock issues, no partial files.
"""
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import settings

logger = logging.getLogger("vitoice.backup")

KEEP_COUNT = 7

_PREFIX = "vitoice-"
_SUFFIX = ".db"


def _db_file_path() -> Path:
    """Filesystem path of the current database (from the sqlalchemy URL)."""
    raw = str(settings.database_url).replace("sqlite+aiosqlite:///", "")
    return Path(raw)


def _backup_files() -> list[Path]:
    """Existing backup files, newest first."""
    try:
        return sorted(
            (p for p in settings.backup_dir.glob(f"{_PREFIX}*{_SUFFIX}") if p.is_file()),
            key=lambda p: p.name,
            reverse=True,
        )
    except OSError:
        return []


def has_backup_today() -> bool:
    """True when at least one backup was created today."""
    today = datetime.now().strftime("%Y%m%d")
    return any(p.name.startswith(f"{_PREFIX}{today}") for p in _backup_files())


def _rotate() -> int:
    """Delete backups beyond KEEP_COUNT. Returns removed count."""
    removed = 0
    for p in _backup_files()[KEEP_COUNT:]:
        try:
            p.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def run_backup_now(reason: str = "manual") -> dict:
    """Create a backup snapshot right now. Never raises — returns ok=False
    with a message on failure so callers can surface it in the UI."""
    src_path = _db_file_path()
    if not src_path.is_file():
        return {"ok": False, "message": f"数据库文件不存在：{src_path}"}
    try:
        settings.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = settings.backup_dir / f"{_PREFIX}{stamp}{_SUFFIX}"
        src = sqlite3.connect(str(src_path))
        try:
            dst = sqlite3.connect(str(dest))
            try:
                with dst:
                    src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        removed = _rotate()
        logger.info("Backup created (%s): %s (rotated %s)", reason, dest, removed)
        return {
            "ok": True,
            "path": str(dest),
            "size": dest.stat().st_size,
            "rotated": removed,
        }
    except (OSError, sqlite3.Error) as exc:
        logger.warning("Backup failed (%s): %s", reason, exc)
        return {"ok": False, "message": str(exc)}


def list_backups() -> list[dict]:
    """Backup inventory for the settings UI (newest first)."""
    result = []
    for p in _backup_files():
        try:
            stat = p.stat()
        except OSError:
            continue
        result.append({"name": p.name, "path": str(p), "size": stat.st_size,
                       "mtime": stat.st_mtime})
    return result
