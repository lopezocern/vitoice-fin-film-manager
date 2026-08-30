"""Application configuration loaded from environment / settings table."""
import logging
import os
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
#   default (prod)   → ~/.vitoice/                   (packaged installer)
#
# This prevents dev sessions from clobbering the production database when
# the app is eventually packaged as an installer. dev.ps1 sets
# VITOICE_ENV=dev; the packaged exe leaves it unset.
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/

if os.getenv("VITOICE_ENV", "prod").lower() == "dev":
    _DATA_ROOT = _BACKEND_DIR / "data"
    _DB_PATH = _DATA_ROOT / "vitoice_dev.db"
    _IS_DEV = True
else:
    _DATA_ROOT = Path.home() / ".vitoice"
    _DB_PATH = _DATA_ROOT / "vitoice.db"
    _IS_DEV = False

logger.info("App env: %s | data root: %s | db: %s",
            "dev" if _IS_DEV else "prod", _DATA_ROOT, _DB_PATH)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VITOICE_", env_file=".env", extra="ignore")

    # Server — bind to 127.0.0.1 by default (local desktop app)
    host: str = "127.0.0.1"
    port: int = 8765
    debug: bool = False  # Default off; enable via VITOICE_DEBUG=true

    # Database — isolated per environment (see _DATA_ROOT / _DB_PATH above)
    database_url: str = f"sqlite+aiosqlite:///{_DB_PATH}"

    # Paths — thumbnails / screenshots / posters live under the data root
    thumbnail_dir: Path = _DATA_ROOT / "thumbnails"
    screenshot_dir: Path = _DATA_ROOT / "screenshots"
    poster_dir: Path = _DATA_ROOT / "posters"
    backdrop_dir: Path = _DATA_ROOT / "backdrops"

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
except OSError:
    import logging
    _log = logging.getLogger("vitoice.config")
    _log.warning(
        "Cannot create data directories under %s — the app may not "
        "function correctly. Check filesystem permissions.", _DATA_ROOT
    )
