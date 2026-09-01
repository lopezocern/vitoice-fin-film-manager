"""Application configuration loaded from environment / settings table."""
import json
import logging
import os
import shutil
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vitoice")

# ---------------------------------------------------------------------------
# Environment isolation: dev vs prod
#
#   VITOICE_ENV=dev  → project-local backend/data/   (development & testing)
#   default (prod)   → data root (see below)         (packaged installer)
#
# This prevents dev sessions from clobbering the production database when
# the app is eventually packaged as an installer. dev.ps1 sets
# VITOICE_ENV=dev; the packaged exe leaves it unset.
# ---------------------------------------------------------------------------
#
# Data root resolution (prod only) — priority:
#   1. VITOICE_DATA_ROOT env var
#   2. pointer file  ~/.vitoice/data-root.json   ({"data_root": "D:\\..."})
#      — written by POST /api/settings/data-root, survives reinstalls
#   3. default       ~/.vitoice/
#
# Directory layout under the data root (layered, Pixcall-style):
#   vitoice.db          metadata (single source of truth)
#   cache/thumbnails    regenerable thumbnails (safe to delete)
#   cache/screenshots   regenerable screenshots
#   assets/posters      scraped posters (recoverable by re-scraping)
#   assets/backdrops    scraped backdrops
#   backups/            automatic daily db backups (rotated)
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/
_DEFAULT_ROOT = Path.home() / ".vitoice"
_POINTER_FILE = _DEFAULT_ROOT / "data-root.json"

# Flat (legacy) dir name → layered destination, relative to the data root.
_LAYERED_DIRS: dict[str, str] = {
    "thumbnails": "cache/thumbnails",
    "screenshots": "cache/screenshots",
    "posters": "assets/posters",
    "backdrops": "assets/backdrops",
}


def _migrate_legacy_layout(root: Path) -> None:
    """One-time migration: flat asset dirs → layered cache/ + assets/.

    Runs at import time, before the engine opens the DB, so paths are
    consistent for the whole process. Never raises — worst case a dir
    stays where it is and the app keeps working off the new path empty.
    """
    for legacy_name, rel_dest in _LAYERED_DIRS.items():
        legacy = root / legacy_name
        if not legacy.is_dir():
            continue
        dest = root / rel_dest
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                # Merge: move children that don't collide, then drop legacy dir
                for child in legacy.iterdir():
                    dst = dest / child.name
                    if not dst.exists():
                        shutil.move(str(child), str(dst))
                try:
                    legacy.rmdir()
                except OSError:
                    pass
            else:
                shutil.move(str(legacy), str(dest))
            logger.info("Migrated legacy dir %s -> %s", legacy, dest)
        except OSError as exc:
            logger.warning("Failed to migrate %s -> %s: %s", legacy, dest, exc)


def _resolve_data_root() -> tuple[Path, str]:
    """Resolve the data root. Returns (path, source) — env|pointer|default."""
    env = os.getenv("VITOICE_DATA_ROOT")
    if env:
        return Path(env).expanduser(), "env"
    try:
        if _POINTER_FILE.is_file():
            data = json.loads(_POINTER_FILE.read_text(encoding="utf-8"))
            raw = str(data.get("data_root") or "").strip()
            if raw:
                return Path(raw).expanduser(), "pointer"
    except (OSError, ValueError) as exc:
        logger.warning("Ignoring unreadable data-root pointer %s: %s", _POINTER_FILE, exc)
    return _DEFAULT_ROOT, "default"


if os.getenv("VITOICE_ENV", "prod").lower() == "dev":
    _DATA_ROOT = _BACKEND_DIR / "data"
    _DB_PATH = _DATA_ROOT / "vitoice_dev.db"
    _IS_DEV = True
    _DATA_ROOT_SOURCE = "dev"
else:
    _DATA_ROOT, _DATA_ROOT_SOURCE = _resolve_data_root()
    _DB_PATH = _DATA_ROOT / "vitoice.db"
    _IS_DEV = False

# Layered layout migration (both dev and prod — dev db path is untouched,
# only regenerable asset dirs move into cache/ + assets/)
try:
    _migrate_legacy_layout(_DATA_ROOT)
except Exception as exc:  # noqa: BLE001 — migration must never block startup
    logger.warning("Legacy layout migration skipped: %s", exc)

logger.info("App env: %s | data root: %s (%s) | db: %s",
            "dev" if _IS_DEV else "prod", _DATA_ROOT, _DATA_ROOT_SOURCE, _DB_PATH)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VITOICE_", env_file=".env", extra="ignore")

    # Server — bind to 127.0.0.1 by default (local desktop app)
    host: str = "127.0.0.1"
    port: int = 8765
    debug: bool = False  # Default off; enable via VITOICE_DEBUG=true

    # Database — isolated per environment (see _DATA_ROOT / _DB_PATH above)
    database_url: str = f"sqlite+aiosqlite:///{_DB_PATH}"

    # Paths — layered under the data root (see module docstring):
    #   cache/  = regenerable, safe to wipe;  assets/ = scraped, re-scrapable
    thumbnail_dir: Path = _DATA_ROOT / "cache" / "thumbnails"
    screenshot_dir: Path = _DATA_ROOT / "cache" / "screenshots"
    poster_dir: Path = _DATA_ROOT / "assets" / "posters"
    backdrop_dir: Path = _DATA_ROOT / "assets" / "backdrops"
    backup_dir: Path = _DATA_ROOT / "backups"

    # External tools
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    ytdlp_path: str = "yt-dlp"

    # Thumbnail defaults
    thumbnail_size: int = 320
    thumbnail_quality: int = 85
    thumbnail_time_offset: float = 10.0  # seconds into the video
    thumbnail_smart_frame: bool = True  # skip black/blank frames when picking the cover

    # Task manager
    max_concurrent_tasks: int = 3
    task_retention_hours: int = 24
    task_timeout_minutes: int = 60  # Max execution time per task

    # AI (OpenAI-compatible)
    ai_api_base: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    ai_model: str = "gpt-4o-mini"
    ai_trigger_on_import: bool = False

    # TMDB scraping (metadata: title / year / overview / poster)
    tmdb_api_key: str = ""  # v3 API key or v4 read access token (starts with eyJ)
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    tmdb_image_base: str = "https://image.tmdb.org/t/p/w500"
    tmdb_language: str = "zh-CN"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:1420", "http://127.0.0.1:1420", "tauri://localhost"]


settings = Settings()

# Ensure directories exist — wrapped in try/except so the app can at least
# start when HOME is unwritable (e.g. restricted Windows environments, M5 fix).
try:
    _DATA_ROOT.mkdir(parents=True, exist_ok=True)
    settings.thumbnail_dir.mkdir(parents=True, exist_ok=True)
    settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
    settings.poster_dir.mkdir(parents=True, exist_ok=True)
    settings.backdrop_dir.mkdir(parents=True, exist_ok=True)
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
except OSError:
    import logging
    _log = logging.getLogger("vitoice.config")
    _log.warning(
        "Cannot create data directories under %s — the app may not "
        "function correctly. Check filesystem permissions.", _DATA_ROOT
    )
