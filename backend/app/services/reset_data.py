"""Reset all application data — the in-app equivalent of a fresh install.

Flow (POST /api/settings/reset-data):
  1. Safety backup of the current DB into ``backups/pre-reset-<ts>.db``
     via the sqlite3 backup API (WAL-safe, consistent while running).
     The ``pre-reset-`` prefix deliberately does NOT match the daily-backup
     glob (``vitoice-*``), so this snapshot is never rotated away by the
     7-copy rotation and never shows up in the daily backup list.
  2. Wipe every user table in the live DB (settings included — a true
     fresh start) via a raw sqlite3 connection with foreign keys off.
     New request sessions on the aiosqlite engine immediately see the
     empty state; no restart required.
  3. Clear the regenerable + scraped asset dirs (cache/thumbnails,
     cache/screenshots, assets/posters, assets/backdrops). The backups
     dir and the data-root pointer file are preserved so the user keeps
     their escape hatch and their chosen data location.

Never raises — returns ok=False with a message on failure.
"""
import logging
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import settings

logger = logging.getLogger("vitoice.reset_data")

# Content dirs cleared on reset (relative to the data root, resolved via
# settings.*_dir so the whitelist matches the running configuration).
_ASSET_DIRS = ("thumbnail_dir", "screenshot_dir", "poster_dir", "backdrop_dir")


def _pre_reset_backup() -> dict:
    """Snapshot the current DB to backups/pre-reset-<ts>.db."""
    db_path = Path(str(settings.database_url).replace("sqlite+aiosqlite:///", ""))
    if not db_path.is_file():
        return {"ok": False, "message": f"数据库文件不存在：{db_path}"}
    try:
        settings.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = settings.backup_dir / f"pre-reset-{stamp}.db"
        src = sqlite3.connect(str(db_path))
        try:
            dst = sqlite3.connect(str(dest))
            try:
                with dst:
                    src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        logger.info("Pre-reset backup created: %s", dest)
        return {"ok": True, "path": str(dest), "size": dest.stat().st_size}
    except (OSError, sqlite3.Error) as exc:
        logger.warning("Pre-reset backup failed: %s", exc)
        return {"ok": False, "message": str(exc)}


def _wipe_db_tables() -> dict:
    """Delete all rows from every user table (settings included), then
    restore the fresh-install seed state.

    Seed parity rules (must match the alembic migrations):
      - ``tag_types`` keeps builtin rows only (is_builtin=1 — the exact
        state right after 001 + 008 seeding); user-created types go.
      - ``settings`` is wiped and re-seeded with the default rows from
        001/010/011/013/014/015 so the settings UI has its base rows
        (runtime values fall back to env/config defaults anyway).
      - ``alembic_version`` is kept (migration state untouched).

    Uses a raw sqlite3 connection with FK enforcement off so deletion
    order doesn't matter.
    """
    db_path = Path(str(settings.database_url).replace("sqlite+aiosqlite:///", ""))
    tables: list[str] = []
    try:
        conn = sqlite3.connect(str(db_path), timeout=30)
        try:
            cur = conn.cursor()
            tables = [
                r[0]
                for r in cur.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            ]
            cur.execute("PRAGMA foreign_keys=OFF")
            with conn:
                for t in tables:
                    if t == "alembic_version":
                        continue  # keep migration state
                    if t == "tag_types":
                        # fresh-install parity: builtin types only
                        cur.execute("DELETE FROM tag_types WHERE NOT is_builtin")
                        continue
                    cur.execute(f'DELETE FROM "{t}"')  # noqa: S608
                # reset AUTOINCREMENT counters when the table exists
                seq = cur.execute(
                    "SELECT name FROM sqlite_master WHERE name='sqlite_sequence'"
                ).fetchone()
                if seq:
                    cur.execute("DELETE FROM sqlite_sequence")
                _reseed_settings(cur)
        finally:
            conn.close()
        logger.info("Wiped %d tables: %s", len(tables), ", ".join(tables))
        return {"ok": True, "tables": tables}
    except (OSError, sqlite3.Error) as exc:
        logger.warning("DB wipe failed: %s", exc)
        return {"ok": False, "message": str(exc), "tables": tables}


# Default settings rows — KEEP IN SYNC with the alembic seeds
# (001_initial, 010, 011, 013, 014, 015). New seeded settings must be
# added here too, otherwise a reset leaves the settings UI without its
# base rows (behavior still falls back to env/config defaults).
_SETTINGS_SEED: tuple[tuple[str, str, str, str, str], ...] = (
    # 001_initial
    ("theme", "system", "string", "appearance", "UI theme: light/dark/system"),
    ("language", "zh-CN", "string", "appearance", "UI language"),
    ("thumbnail_size", "320", "int", "thumbnail", "Thumbnail width in pixels"),
    ("thumbnail_quality", "85", "int", "thumbnail", "Thumbnail JPEG quality"),
    ("thumbnail_time_offset", "10.0", "float", "thumbnail", "Thumbnail capture time offset (seconds)"),
    ("ffmpeg_path", "ffmpeg", "path", "tools", "ffmpeg binary path"),
    ("ffprobe_path", "ffprobe", "path", "tools", "ffprobe binary path"),
    ("ytdlp_path", "yt-dlp", "path", "tools", "yt-dlp binary path"),
    ("ai_api_base", "https://api.openai.com/v1", "string", "ai", "AI API base URL"),
    ("ai_api_key", "", "string", "ai", "AI API key"),
    ("ai_model", "gpt-4o-mini", "string", "ai", "AI model name"),
    ("ai_trigger_on_import", "0", "bool", "ai", "Auto-trigger AI tagging on import"),
    ("step_size", "5", "float", "player", "Arrow key step size (seconds)"),
    ("step_unit", "seconds", "string", "player", "Step unit: seconds/frames"),
    ("subtitle_font_size", "16", "int", "subtitle", "Subtitle font size"),
    ("subtitle_color", "#FFFFFF", "string", "subtitle", "Subtitle text color"),
    ("subtitle_stroke", "2", "int", "subtitle", "Subtitle stroke width"),
    ("subtitle_bg_opacity", "0.5", "float", "subtitle", "Subtitle background opacity"),
    ("subtitle_position", "bottom", "string", "subtitle", "Subtitle position"),
    # 010 show_restricted
    ("show_restricted", "false", "bool", "content",
     "Show restricted content (AV/adult libraries). When off, restricted libraries are hidden from all views."),
    # 011 mask_restricted
    ("mask_restricted", "false", "bool", "content",
     "Mask restricted content posters and video with blur overlay. Only effective when show_restricted is enabled."),
    # 013 scrape_sources
    ("scrape_sources", '{"movie": [], "tv": [], "av": []}', "json", "scrape",
     "Unified scraping source chains (movie/tv/av). Empty arrays fall back to built-in defaults."),
    # 014 adult network
    ("network_allow_adult", "false", "bool", "content",
     "Allow resolving adult aggregator network sources (javgg-style). When off, the resolver endpoint is disabled."),
    ("network_adult_base_url", "https://javgg.net", "string", "content",
     "Root URL of the adult aggregator site used for network source resolution."),
    # 015 proxy
    ("proxy_enabled", "false", "bool", "tools",
     "Route outbound requests (scraping, aggregator, AI) through an HTTP proxy. Off = direct connection."),
    ("proxy_host", "", "string", "tools", "Proxy host (IP or hostname)."),
    ("proxy_port", "7890", "string", "tools", "Proxy port."),
)


def _reseed_settings(cur: sqlite3.Cursor) -> None:
    """Re-insert default settings rows (INSERT OR IGNORE — user rows that
    survived any future partial-wipe change are never clobbered)."""
    cur.executemany(
        "INSERT OR IGNORE INTO settings (key, value, type, category, description) "
        "VALUES (?, ?, ?, ?, ?)",
        _SETTINGS_SEED,
    )


def _clear_asset_dirs() -> dict:
    """Remove the *contents* of the managed asset dirs (dirs themselves stay)."""
    removed_files = 0
    freed_bytes = 0
    errors: list[str] = []
    roots: list[Path] = []
    for attr in _ASSET_DIRS:
        d: Path = getattr(settings, attr)
        try:
            roots.append(d.resolve())
        except (OSError, RuntimeError):
            continue
    for attr in _ASSET_DIRS:
        d: Path = getattr(settings, attr)
        if not d.is_dir():
            continue
        resolved = d.resolve()
        # S1 whitelist: only ever delete inside the managed dirs
        if not any(resolved == r or r in resolved.parents for r in roots):
            continue
        for child in d.iterdir():
            try:
                if child.is_dir():
                    size = sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
                    shutil.rmtree(child)
                else:
                    size = child.stat().st_size
                    child.unlink()
                removed_files += 1
                freed_bytes += size
            except OSError as exc:
                errors.append(f"{child.name}: {exc}")
    if errors:
        logger.warning("Asset dir cleanup had errors: %s", errors[:5])
    return {
        "ok": not errors,
        "removed_files": removed_files,
        "freed_bytes": freed_bytes,
        "errors": errors,
    }


def reset_all_data() -> dict:
    """Full reset: pre-reset backup → wipe tables → clear asset dirs."""
    backup = _pre_reset_backup()
    if not backup.get("ok"):
        # Refuse to wipe without a safety snapshot — the backup IS the
        # undo path for this destructive operation.
        return {"ok": False, "message": f"重置前备份失败，已中止：{backup.get('message', '')}"}

    wipe = _wipe_db_tables()
    if not wipe.get("ok"):
        return {
            "ok": False,
            "message": f"数据清空失败（备份已保留在 {backup['path']}）：{wipe.get('message', '')}",
            "backup_path": backup["path"],
        }

    assets = _clear_asset_dirs()
    logger.info(
        "Data reset complete: backup=%s tables=%d files=%d freed=%d",
        backup["path"], len(wipe.get("tables", [])),
        assets["removed_files"], assets["freed_bytes"],
    )
    return {
        "ok": True,
        "message": "所有数据已清空（重置前备份已保留）",
        "backup_path": backup["path"],
        "tables_cleared": len(wipe.get("tables", [])),
        "removed_files": assets["removed_files"],
        "freed_bytes": assets["freed_bytes"],
        "asset_errors": assets["errors"],
    }
