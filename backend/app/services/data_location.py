"""Custom data-root support — query and change where vitoice stores data.

Resolution order (see app.config): VITOICE_DATA_ROOT env > pointer file
(~/.vitoice/data-root.json) > default ~/.vitoice.

``change_data_root`` migrates the whole data set to a new location:
  1. validate the target (writable, not the current root, not an existing
     vitoice data dir);
  2. snapshot-copy the DB with the sqlite3 backup API (WAL-safe) so the
     copy is consistent even while the app is running;
  3. move the layered asset dirs (cache/ assets/ backups/);
  4. write the pointer file — the new root takes effect after restart.

The old root's ``vitoice.db`` is intentionally left in place as a safety
copy and can be removed manually once the new location is verified.
"""
import json
import logging
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app import config

logger = logging.getLogger("vitoice.data_location")

_DATA_DIR_NAMES = ("cache", "assets", "backups")


def get_data_location_info() -> dict:
    """Current data-root facts for the settings UI."""
    env_override = bool(os.getenv("VITOICE_DATA_ROOT"))
    return {
        "current": str(config._DATA_ROOT),
        "default": str(config._DEFAULT_ROOT),
        "source": config._DATA_ROOT_SOURCE,  # dev | env | pointer | default
        "env_override": env_override,
        "pointer_file": str(config._POINTER_FILE),
        "db_path": str(config._DB_PATH),
        "is_dev": config._IS_DEV,
    }


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".vitoice-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _looks_like_existing_data_dir(target: Path) -> bool:
    """Reject targets that already hold a vitoice dataset (avoid clobbering)."""
    if (target / "vitoice.db").exists() or (target / "vitoice_dev.db").exists():
        return True
    return all((target / name).is_dir() for name in ("cache", "assets"))


def change_data_root(new_root: str) -> dict:
    """Migrate data to ``new_root`` and persist the choice via pointer file.

    Returns ``{"ok": bool, "message": str, ...}`` — ok=True means the caller
    should prompt the user to restart the app.
    """
    if config._IS_DEV:
        return {"ok": False,
                "message": "开发环境（VITOICE_ENV=dev）固定使用 backend/data，不支持更改"}
    if config._DATA_ROOT_SOURCE == "env":
        return {"ok": False,
                "message": "VITOICE_DATA_ROOT 环境变量已设置，指针文件不生效；请先移除该环境变量"}

    try:
        target = Path(new_root).expanduser()
        if not target.is_absolute():
            target = Path(os.path.abspath(target))
    except (OSError, RuntimeError) as exc:
        return {"ok": False, "message": f"路径无效：{exc}"}

    current = config._DATA_ROOT
    if target == current:
        return {"ok": False, "message": "新位置与当前数据目录相同"}
    if not _is_writable_dir(target):
        return {"ok": False, "message": f"目标目录不可写：{target}"}
    if _looks_like_existing_data_dir(target):
        return {"ok": False, "message": "目标目录已存在 vitoice 数据（vitoice.db 或 cache/assets），请换一个空目录"}

    # 1. Snapshot-copy the DB (consistent even with the live engine + WAL)
    db_src = Path(config._DB_PATH)
    if not db_src.is_file():
        return {"ok": False, "message": f"数据库文件不存在：{db_src}"}
    db_dest = target / "vitoice.db"
    try:
        src = sqlite3.connect(str(db_src))
        try:
            dst = sqlite3.connect(str(db_dest))
            try:
                with dst:
                    src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    except (OSError, sqlite3.Error) as exc:
        # Clean up the partial copy so the target stays empty
        try:
            db_dest.unlink(missing_ok=True)
        except OSError:
            pass
        return {"ok": False, "message": f"数据库复制失败：{exc}"}

    # 2. Move layered asset dirs (same volume = instant rename; cross volume
    #    = shutil falls back to copy+delete)
    moved: list[str] = []
    for name in _DATA_DIR_NAMES:
        src_dir = current / name
        dest_dir = target / name
        if src_dir.is_dir() and not dest_dir.exists():
            try:
                shutil.move(str(src_dir), str(dest_dir))
                moved.append(name)
            except OSError as exc:
                logger.warning("Could not move %s to new root: %s", src_dir, exc)

    # 3. Persist the choice — pointer file lives at the fixed default anchor
    try:
        config._POINTER_FILE.parent.mkdir(parents=True, exist_ok=True)
        config._POINTER_FILE.write_text(
            json.dumps({
                "data_root": str(target),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        # Roll back nothing silently — db copy exists but won't be picked up.
        return {"ok": False, "message": f"写入指针文件失败（{config._POINTER_FILE}）：{exc}"}

    logger.info("Data root change prepared: %s -> %s (moved: %s)",
                current, target, moved)
    return {
        "ok": True,
        "message": "数据已迁移到新位置，重启应用后生效",
        "restart_required": True,
        "old_root": str(current),
        "new_root": str(target),
        "moved_dirs": moved,
        "note": "旧位置的 vitoice.db 保留作为安全副本，确认新位置正常后可手动删除",
    }
