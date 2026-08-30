"""TMDB scraping service — fetch title / year / overview / poster.

Config resolution order (highest priority first):
1. Explicit overrides passed into resolve_tmdb_config() (used by the
   "test connection" endpoint so it can validate exactly what the user typed).
2. Database `settings` table (what the user saved in the UI).
3. Environment-based app.config.settings defaults.

Authentication:
- TMDB v3 API key  -> passed as `api_key` query parameter.
- TMDB v4 read token (JWT, starts with "eyJ") -> passed as `Authorization: Bearer`.

The scraper is fault tolerant in the batch/pipeline path (never raises), but a
checked variant is provided for the settings "test" endpoint so the UI can show
a specific reason on failure.
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.services.proxy import get_proxy_url
from app.database import async_session
from app.models.enums import ScrapeMode
from app.models.library import MediaLibrary
from app.models.media import Media
from app.models.series import Series
from app.models.setting import Setting
from app.models.tag import Tag, TagType, VideoTag

logger = logging.getLogger("vitoice.scraper")

# Release-group / quality / codec noise tokens stripped from filenames before
# building the TMDB search query.
_NOISE_TOKENS = {
    "1080p", "720p", "2160p", "480p", "4k", "8k", "uhd", "hd", "sd",
    "bluray", "blu-ray", "bdrip", "brrip", "dvdrip", "dvd", "webrip",
    "web-dl", "webdl", "web", "hdtv", "hdrip", "remux", "proper", "repack",
    "x264", "x265", "h264", "h265", "hevc", "avc", "xvid", "divx",
    "aac", "ac3", "dts", "dts-hd", "truehd", "flac", "mp3", "ddp", "dd5",
    "10bit", "8bit", "hdr", "hdr10", "dolby", "atmos", "sdr",
    "extended", "unrated", "directors", "cut", "imax", "remastered",
    "internal", "limited", "multi", "dual", "audio",
}

# Tokens after which everything is considered noise (season/episode markers etc).
# Includes seasonless patterns (E05, EP05, Episode 5, 第5集, 第5话) so titles
# are truncated before them.
_STOP_PATTERNS = re.compile(
    r"(?:"
    r"\b(?:s\d{1,2}e\d{1,2}|season\s*\d+|ep?\d{1,3}|episode\s*\d+|part\s*\d+)\b"
    r"|第\d+季\s*第\d+集|第\d+集|第\d+[话話]"
    r")",
    re.IGNORECASE,
)


class TMDBConfigError(Exception):
    """Raised when TMDB configuration is incomplete (e.g. missing API key)."""


@dataclass
class TMDBConfig:
    api_key: str
    base_url: str
    image_base: str
    language: str


def resolve_tmdb_config(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    image_base: str | None = None,
    language: str | None = None,
    db_rows: dict[str, str] | None = None,
) -> TMDBConfig:
    """Merge overrides -> DB settings -> env defaults into a TMDBConfig."""
    db_rows = db_rows or {}

    key = api_key if api_key is not None else db_rows.get("tmdb_api_key")
    if not key:
        key = settings.tmdb_api_key
    key = (key or "").strip()

    base = base_url if base_url is not None else db_rows.get("tmdb_base_url")
    base = (base or "").strip() or settings.tmdb_base_url
    base = base.rstrip("/")

    img = image_base if image_base is not None else db_rows.get("tmdb_image_base")
    img = (img or "").strip() or settings.tmdb_image_base
    img = img.rstrip("/")

    lang = language if language is not None else db_rows.get("tmdb_language")
    lang = (lang or "").strip() or settings.tmdb_language

    return TMDBConfig(api_key=key, base_url=base, image_base=img, language=lang)


async def _load_tmdb_config_from_db() -> TMDBConfig:
    keys = ["tmdb_api_key", "tmdb_base_url", "tmdb_image_base", "tmdb_language"]
    async with async_session() as session:
        result = await session.execute(select(Setting).where(Setting.key.in_(keys)))
        rows = {s.key: (s.value or "") for s in result.scalars().all()}
    return resolve_tmdb_config(db_rows=rows)


# =====================================================================
# Unified scrape source chains (movie / tv / av)
#
# Sources live in the `settings.scrape_sources` JSON key, grouped by
# content kind. Each group is an ordered fallback chain; the scraper
# tries sources in array order and switches to the next on failure.
#
# Isolation contract (normal vs adult content):
#   - load_scrape_sources(kind) ONLY reads the matching group.
#   - movie/tv chains can only contain kind="tmdb" sources;
#     the av chain can only contain kind="html" sources.
#   - Empty group -> built-in defaults (TMDB from tmdb_* keys for
#     movie/tv; JavBus->JavDB->JavLibrary inside av_scraper for av).
# =====================================================================

_SCRAPE_KINDS = ("movie", "tv", "av")
_SCRAPE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


@dataclass
class ScrapeSource:
    """A single scrape source entry in a fallback chain."""

    name: str
    kind: str  # "tmdb" (TMDB-compatible API) | "html" (html page scraping)
    base_url: str = ""
    image_base: str = ""
    api_key: str = ""
    language: str = ""
    timeout: int = 30
    enabled: bool = True
    parser: str = ""  # av only: "javbus" | "javdb" | "javlibrary" (auto-inferred when empty)


def parse_scrape_sources(raw_json: str | None, kind: str) -> list[ScrapeSource]:
    """Parse one kind's source list from the ``scrape_sources`` JSON value.

    Returns an empty list on missing / malformed JSON or an unknown kind —
    callers then fall back to built-in defaults. Never raises.
    """
    if kind not in _SCRAPE_KINDS:
        return []
    if not raw_json:
        return []
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return []
    items = data.get(kind) if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    out: list[ScrapeSource] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            src = ScrapeSource(
                name=str(it.get("name") or "").strip() or "未命名源",
                kind=it.get("kind") if it.get("kind") in ("tmdb", "html") else "tmdb",
                base_url=str(it.get("base_url") or "").strip(),
                image_base=str(it.get("image_base") or "").strip(),
                api_key=str(it.get("api_key") or "").strip(),
                language=str(it.get("language") or "").strip(),
                timeout=int(it.get("timeout") or 30),
                enabled=bool(it.get("enabled", True)),
                parser=str(it.get("parser") or "").strip().lower(),
            )
        except (TypeError, ValueError):
            continue
        if src.base_url:
            out.append(src)
    return out


async def load_scrape_sources(kind: str) -> list[ScrapeSource]:
    """Load the enabled fallback chain for a content kind.

    Returns the configured sources when ``scrape_sources[kind]`` is
    non-empty; otherwise an empty list (built-in defaults apply:
    movie/tv use the tmdb_* settings, av uses av_scraper defaults).
    """
    if kind not in _SCRAPE_KINDS:
        return []
    async with async_session() as session:
        result = await session.execute(
            select(Setting.value).where(Setting.key == "scrape_sources")
        )
        raw = result.scalar()
    sources = parse_scrape_sources(raw, kind)
    return [s for s in sources if s.enabled]


def _source_to_tmdb_config(
    src: ScrapeSource, base: TMDBConfig
) -> TMDBConfig:
    """Build a TMDBConfig from a source, inheriting blank fields from the
    global TMDB settings (mirror / proxy scenarios only override some fields)."""
    return TMDBConfig(
        api_key=(src.api_key or base.api_key),
        base_url=(src.base_url.rstrip("/") or base.base_url),
        image_base=(src.image_base.rstrip("/") or base.image_base),
        language=(src.language or base.language),
    )


async def test_scrape_source(
    src: ScrapeSource, kind: str
) -> tuple[bool, str]:
    """Validate a single scrape source connectivity. Never raises.

    tmdb kind -> GET {base}/search/movie?query=matrix (needs api key).
    html kind -> GET {base}/ root page and check HTTP 200.
    """
    if kind == "av":
        url = src.base_url.rstrip("/") + "/"
        try:
            async with httpx.AsyncClient(timeout=max(src.timeout, 5), proxy=await get_proxy_url()) as client:
                resp = await client.get(
                    url, headers={"User-Agent": _SCRAPE_UA}, follow_redirects=True
                )
                resp.raise_for_status()
            return True, f"{src.name}: 连接成功 (HTTP {resp.status_code})"
        except httpx.HTTPStatusError as exc:
            return False, f"{src.name}: HTTP {exc.response.status_code}"
        except Exception as exc:  # noqa: BLE001
            return False, f"{src.name}: {exc}"

    # tmdb kind (movie / tv groups)
    base = await _load_tmdb_config_from_db()
    cfg = _source_to_tmdb_config(src, base)
    if not cfg.api_key:
        return False, f"{src.name}: 未配置 API Key"
    headers, params = _auth(cfg)
    params = {**params, "query": "matrix", "language": cfg.language}
    try:
        async with httpx.AsyncClient(timeout=max(src.timeout, 5), proxy=await get_proxy_url()) as client:
            resp = await client.get(
                f"{cfg.base_url}/search/movie", headers=headers, params=params
            )
            resp.raise_for_status()
            n = len(resp.json().get("results") or [])
        return True, f"{src.name}: 连接成功（返回 {n} 条结果）"
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        hint = {
            401: "API Key 无效或未授权",
            403: "禁止访问（源可能拒绝请求）",
            404: "地址路径无效",
            429: "请求过于频繁",
        }.get(code, "HTTP 错误")
        return False, f"{src.name}: {hint} ({code})"
    except Exception as exc:  # noqa: BLE001
        return False, f"{src.name}: {exc}"


def _auth(cfg: TMDBConfig) -> tuple[dict, dict]:
    """Return (headers, base_params) for the configured auth style."""
    if cfg.api_key.startswith("eyJ"):  # v4 read access token (JWT)
        return {"Authorization": f"Bearer {cfg.api_key}"}, {}
    return {}, {"api_key": cfg.api_key}  # v3 API key


def parse_filename(name: str) -> tuple[str, int | None, int | None, int | None]:
    """Parse a media file name into a clean (title, year, season, episode) tuple.

    Handles common release naming: dots/underscores as separators, a 4-digit
    year, season/episode markers, and trailing quality/codec noise.
    Returns (title, year|None, season_number|None, episode_number|None).

    Season+Episode patterns detected:
        S01E05, Season 1 Episode 5, 第1季第5集

    Seasonless patterns (default season = 1):
        E05, EP05, Episode 5, 第5集, 第5话

    Examples:
        "The.Matrix.1999.1080p.BluRay.x264.mkv" -> ("The Matrix", 1999, None, None)
        "Show.Name.S01E05.1080p.mkv"              -> ("Show Name", None, 1, 5)
        "Show.Name.E05.1080p.mkv"                 -> ("Show Name", None, 1, 5)
        "剧名.第5集.mkv"                           -> ("剧名", None, 1, 5)
        "电影名 (2021).mp4"                         -> ("电影名", 2021, None, None)
        "Some Movie.mkv"                            -> ("Some Movie", None, None, None)
    """
    stem = Path(name).stem
    # Normalise separators; turn bracket characters into spaces so a bracketed
    # year like "(2021)" degrades cleanly to a bare token before extraction.
    text = re.sub(r"[._]+", " ", stem)
    text = re.sub(r"[\(\)\[\]\{\}]", " ", text)
    # Trim at Chinese/Japanese colon subtitles and numbered editions:
    #   "名侦探柯南剧场版01：引爆摩天楼" → "名侦探柯南剧场版01"
    #   "Movie Title 02：Some Subtitle"      → "Movie Title 02"
    # Keep the base including the number (e.g. "剧场版01") so year-less
    # editions can still be distinguished from similarly named titles.
    text = re.sub(r"[：:]\s*[^：:]*$", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()

    # Detect season/episode patterns before cutting them off
    season_number: int | None = None
    episode_number: int | None = None

    # --- Season + Episode patterns ---
    se_match = re.search(r"(?i)s(\d{1,2})[\s._-]*e(\d{1,2})", text)
    if not se_match:
        se_match = re.search(r"(?i)season\s+(\d{1,2})\s+episode\s+(\d{1,2})", text)
    if not se_match:
        # Chinese: 第1季第5集 (allow optional separator between 季 and 第)
        se_match = re.search(r"第(\d{1,2})季\s*第(\d{1,3})集", text)
    if se_match:
        season_number = int(se_match.group(1))
        episode_number = int(se_match.group(2))
    else:
        # --- Seasonless episode patterns (default season = 1) ---
        # English: E05, EP05, Episode 5 (must be preceded by separator)
        ep_match = re.search(r"(?i)(?:^|\s)(?:ep?|episode)\s*(\d{1,3})(?!\d)", text)
        if not ep_match:
            # Chinese: 第5集 (no season prefix)
            ep_match = re.search(r"第(\d{1,3})集", text)
        if not ep_match:
            # Japanese/Chinese: 第5话, 第5話
            ep_match = re.search(r"第(\d{1,3})[话話]", text)
        if ep_match:
            season_number = 1  # default season for seasonless shows
            episode_number = int(ep_match.group(1))

    # Cut off season/episode markers and everything after
    m = _STOP_PATTERNS.search(text)
    if m:
        text = text[: m.start()].strip()

    year: int | None = None
    # Find a plausible year (1900-2099); prefer the last one (release year is
    # usually after the title, and titles rarely end in a bare year).
    year_matches = list(re.finditer(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", text))
    if year_matches:
        last = year_matches[-1]
        year = int(last.group(1))
        # Title is everything before the year
        text = text[: last.start()].strip()

    # Drop trailing noise tokens
    tokens = [t for t in re.split(r"\s+", text) if t]
    cleaned: list[str] = []
    for tok in tokens:
        if tok.lower().strip("-") in _NOISE_TOKENS:
            # Stop at the first noise token — the real title precedes it
            break
        cleaned.append(tok)

    title = " ".join(cleaned).strip(" -") or stem
    return title, year, season_number, episode_number


# --- Parent directory fallback helpers ---
# Shared with series_aggregator.py — kept here to avoid circular imports.

_EPISODE_MARKER_RE = re.compile(
    r"^(?:第\d{1,3}[集话話]|[Ee][Pp]?\d{1,3}|[Ee]pisode\s*\d{1,3})$"
)

def _is_episode_marker_title(title: str) -> bool:
    """True if the title is just an episode marker (e.g. '第1集', 'E05')."""
    return bool(_EPISODE_MARKER_RE.match(title.strip()))

_SEASON_DIR_PATTERNS = [
    re.compile(r"第(\d{1,2})季"),                      # Arabic: 第1季
    re.compile(r"第([一二三四五六七八九十]+)季"),        # Chinese numerals: 第一季, 第十季
    re.compile(r"[Ss](?:eason)?\s*(\d{1,2})"),          # English: Season 1, S1
]

_CN_NUM_MAP = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _cn_num_to_int(s: str) -> int:
    """Convert a Chinese numeral string (1–99) to int.

    Handles: 一(1)…十(10), 十一(11)…十九(19), 二十(20), 二十一(21)…九十九(99).
    """
    if not s:
        return 0
    if len(s) == 1:
        return _CN_NUM_MAP.get(s, 0)
    if s[0] == "十":
        return 10 + _CN_NUM_MAP.get(s[1:], 0)
    if s[-1] == "十":
        return _CN_NUM_MAP.get(s[:-1], 0) * 10
    if "十" in s:
        parts = s.split("十")
        return _CN_NUM_MAP.get(parts[0], 0) * 10 + _CN_NUM_MAP.get(parts[1], 0)
    return 0


def _parse_parent_dir_for_title(file_path: str) -> tuple[str, int | None]:
    """Extract show title and season from the parent directory name.

    Supports Arabic digits (第1季, Season 2, S3) and Chinese numerals
    (第一季, 第十二季).

    When the parent directory is *only* a season marker (e.g. "第一季",
    "Season 2") with no show name, walks up to the grandparent directory
    to find the show title. This handles the common layout:

        库/剧名/第一季/第1集.mp4   → ("剧名", 1)
        库/剧名/Season 2/E05.mkv  → ("剧名", 2)
    """
    p = Path(file_path).parent
    parent = p.name
    text = re.sub(r"[._]+", " ", parent).strip()
    season: int | None = None
    for pat in _SEASON_DIR_PATTERNS:
        m = pat.search(text)
        if m:
            raw = m.group(1)
            season = int(raw) if raw.isdigit() else _cn_num_to_int(raw)
            text = (text[:m.start()] + " " + text[m.end():]).strip()
            break
    text = re.sub(r"\s+", " ", text).strip(" -")

    if text:
        # Parent directory had a show name (possibly with season info).
        return text, season

    # Parent directory was *only* a season marker — use grandparent.
    grandparent = p.parent.name
    if grandparent and grandparent not in ("", "/", "\\"):
        gp_text = re.sub(r"[._]+", " ", grandparent).strip()
        # Strip trailing season markers from grandparent too (e.g. "庆余年 第一季")
        for pat in _SEASON_DIR_PATTERNS:
            m = pat.search(gp_text)
            if m:
                gp_text = (gp_text[:m.start()] + " " + gp_text[m.end():]).strip()
                if season is None:
                    raw = m.group(1)
                    season = int(raw) if raw.isdigit() else _cn_num_to_int(raw)
                break
        gp_text = re.sub(r"\s+", " ", gp_text).strip(" -")
        if gp_text:
            return gp_text, season

    return (text or parent), season


async def _tmdb_search(
    client: httpx.AsyncClient, cfg: TMDBConfig, kind: str, query: str, year: int | None
) -> dict | None:
    """Search TMDB for a movie or tv show. Returns the first result or None."""
    headers, params = _auth(cfg)
    # include_adult=false: movie/tv 库不应搜回成人条目（成人内容只走 AV 库隔离链路）
    params = {**params, "query": query, "language": cfg.language, "include_adult": "false"}
    if year:
        params["year" if kind == "movie" else "first_air_date_year"] = year

    url = f"{cfg.base_url}/search/{kind}"
    resp = await client.get(url, headers=headers, params=params)
    resp.raise_for_status()
    results = resp.json().get("results") or []
    return results[0] if results else None


async def _tmdb_detail(
    client: httpx.AsyncClient, cfg: TMDBConfig, kind: str, tmdb_id: int
) -> dict:
    """Fetch full detail for a movie/tv id (for a richer overview)."""
    headers, params = _auth(cfg)
    params = {**params, "language": cfg.language}
    url = f"{cfg.base_url}/{kind}/{tmdb_id}"
    resp = await client.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()


async def _tmdb_credits(
    client: httpx.AsyncClient, cfg: TMDBConfig, kind: str, tmdb_id: int
) -> dict:
    """Fetch cast & crew credits for a movie/tv id."""
    headers, params = _auth(cfg)
    params = {**params, "language": cfg.language}
    url = f"{cfg.base_url}/{kind}/{tmdb_id}/credits"
    resp = await client.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()


def _scrape_kind(scrape_mode: ScrapeMode) -> str:
    """Map a library ScrapeMode to a TMDB search kind (movie|tv)."""
    return "tv" if scrape_mode == ScrapeMode.TV else "movie"


async def _download_poster(
    client: httpx.AsyncClient, cfg: TMDBConfig, poster_path: str, media_id: int
) -> str | None:
    """Download a TMDB poster image to the local poster dir. Returns path."""
    if not poster_path:
        return None
    url = f"{cfg.image_base}{poster_path}"
    resp = await client.get(url)
    resp.raise_for_status()
    settings.poster_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.poster_dir / f"{media_id}.jpg"
    await asyncio.to_thread(dest.write_bytes, resp.content)
    return str(dest)


async def _download_poster_series(
    cfg: TMDBConfig, poster_path: str, series_id: int
) -> str | None:
    """Download a TMDB poster for a Series (shared across all episodes).

    Uses ``series_{id}.jpg`` as the filename so it's distinct from
    per-media posters and won't collide when media IDs are reused.
    Creates its own HTTP client since it's called outside the main scrape
    HTTP context (inside the DB session block).
    """
    if not poster_path:
        return None
    url = f"{cfg.image_base}{poster_path}"
    async with httpx.AsyncClient(timeout=30, proxy=await get_proxy_url()) as client:
        resp = await client.get(url)
        resp.raise_for_status()
    settings.poster_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.poster_dir / f"series_{series_id}.jpg"
    await asyncio.to_thread(dest.write_bytes, resp.content)
    return str(dest)


@dataclass
class ScrapeResult:
    matched: bool
    title: str | None = None
    year: int | None = None
    overview: str | None = None
    poster_path: str | None = None
    genre_count: int = 0
    season_number: int | None = None
    episode_number: int | None = None
    message: str = ""


async def _get_or_create_tag_type(session, name: str, *, sort_order: int, is_builtin: bool = False, color: str | None = None) -> TagType:
    """Find or create a TagType by name, aligning with seed-data conventions."""
    result = await session.execute(select(TagType).where(TagType.name == name))
    tag_type = result.scalar_one_or_none()
    if not tag_type:
        kwargs: dict = {"name": name, "sort_order": sort_order, "is_builtin": is_builtin}
        if color:
            kwargs["color"] = color
        tag_type = TagType(**kwargs)
        session.add(tag_type)
        await session.flush()
    return tag_type


async def _sync_tags_for_media(
    session,
    media_id: int,
    tag_specs: list[tuple[str, str]],
    source: str = "scrape",
) -> int:
    """Find/create tags and attach them to a media item.

    ``tag_specs`` is a list of ``(tag_name, type_name)`` pairs, e.g.
    ``[("Action", "genre"), ("Daniel Radcliffe", "actor")]``.

    The function ensures TagType / Tag / VideoTag rows exist, skipping
    duplicates.  Returns the number of new VideoTag associations created.
    """
    if not tag_specs:
        return 0

    # Group specs by type name to batch-load/create tag types
    type_names = sorted({spec[1] for spec in tag_specs})

    # Seed-data aligned defaults: (sort_order, is_builtin, color)
    type_defaults: dict[str, tuple[int, bool, str | None]] = {
        "actor": (0, True, "#635bff"),
        "genre": (1, True, "#f59e0b"),
        "theme": (2, True, "#34c759"),
        "custom": (3, True, "#8e8e93"),
        "collection": (4, True, "#27D2BF"),
        "studio": (5, False, "#5856D6"),
        # AV-specific tag types — isolated from movie/TV tags to prevent
        # namespace pollution (AV has thousands of actresses/studios)
        "av_actress": (10, True, "#af52de"),
        "av_genre": (11, True, "#ff3b30"),
        "av_studio": (12, True, "#5856D6"),
        "av_series": (13, True, "#007aff"),
        "av_director": (14, True, "#5ac8fa"),
    }

    type_map: dict[str, TagType] = {}
    for tn in type_names:
        so, ib, col = type_defaults.get(tn, (99, False, None))
        type_map[tn] = await _get_or_create_tag_type(
            session, tn, sort_order=so, is_builtin=ib, color=col
        )

    # Batch-load existing tags by name within their respective types
    # Build (name, tag_type_id) pairs for lookup
    name_type_pairs = [(name, type_map[tn].id) for name, tn in tag_specs]

    # Load all candidate tags in one query per type
    existing_tags: dict[tuple[str, int], Tag] = {}
    for tn, tt in type_map.items():
        names_for_type = [name for name, tname in tag_specs if tname == tn]
        if not names_for_type:
            continue
        result = await session.execute(
            select(Tag).where(
                Tag.name.in_(names_for_type),
                Tag.tag_type_id == tt.id,
            )
        )
        for t in result.scalars().all():
            existing_tags[(t.name, tt.id)] = t

    # Create missing tags
    for name, tn in tag_specs:
        tt = type_map[tn]
        key = (name, tt.id)
        if key not in existing_tags:
            tag = Tag(name=name, tag_type_id=tt.id)
            session.add(tag)
            await session.flush()
            existing_tags[key] = tag

    # Check existing VideoTag associations (skip duplicates)
    all_tag_ids = [t.id for t in existing_tags.values()]
    result = await session.execute(
        select(VideoTag).where(
            VideoTag.media_id == media_id,
            VideoTag.tag_id.in_(all_tag_ids),
        )
    )
    attached_ids = {vt.tag_id for vt in result.scalars().all()}

    # Create new VideoTag rows
    count = 0
    for tag in existing_tags.values():
        if tag.id not in attached_ids:
            vt = VideoTag(media_id=media_id, tag_id=tag.id, source=source)
            session.add(vt)
            count += 1
    if count:
        await session.flush()

    # ---- 系列标签继承：电视剧子剧集共享同一组标签 ----
    # 刮削通常只命中一集，若该集属于某 Series（series_id 非空），把同样的标签
    # 同步到同系列的其他集——避免"系列下只有刮削过的那集有标签，其余子剧集缺标签"。
    if count > 0:
        media_row = await session.get(Media, media_id)
        if media_row is not None and media_row.series_id is not None:
            # 同系列全部集（含本集，去重后跳过已有）
            result = await session.execute(
                select(Media.id).where(
                    Media.series_id == media_row.series_id,
                    Media.is_deleted == False,  # noqa: E712
                )
            )
            sibling_ids = [row[0] for row in result.all() if row[0] != media_id]
            if sibling_ids:
                # 批量查询这些集已有哪些标签，避免重复
                result = await session.execute(
                    select(VideoTag.media_id, VideoTag.tag_id).where(
                        VideoTag.media_id.in_(sibling_ids),
                        VideoTag.tag_id.in_(all_tag_ids),
                    )
                )
                existing_pairs = {(vt.media_id, vt.tag_id) for vt in result.all()}
                inherited = 0
                for sibling_id in sibling_ids:
                    for tag in existing_tags.values():
                        if (sibling_id, tag.id) not in existing_pairs:
                            session.add(VideoTag(media_id=sibling_id, tag_id=tag.id, source=source))
                            inherited += 1
                if inherited:
                    await session.flush()
                    count += inherited
    return count


async def scrape_media(
    media_id: int,
    cfg: TMDBConfig | None = None,
    *,
    query_override: str | None = None,
    year_override: int | None = None,
) -> ScrapeResult:
    """Scrape a single media item and persist the metadata.

    Routes to the AV scraper for ``ScrapeMode.AV`` libraries, or the TMDB
    scraper for MOVIE / TV.  Writes back title / year / description / poster
    when a match is found.  Returns a ScrapeResult describing the outcome.
    Never raises for "no match"; raises TMDBConfigError / httpx errors only
    for hard failures so the caller can decide how to surface them.

    When ``query_override`` (and optionally ``year_override``) is supplied,
    the filename parser is bypassed and the given title/year are used
    directly as the TMDB search query. This is used by the AI-rescrape
    endpoint to recover from filenames the regex parser misreads.
    """
    # --- Phase 0: load media + library to determine scrape mode ---
    async with async_session() as session:
        media = await session.get(Media, media_id)
        if not media:
            return ScrapeResult(matched=False, message="media not found")
        lib = await session.get(MediaLibrary, media.library_id)
        scrape_mode = lib.scrape_mode if lib else ScrapeMode.MOVIE
        source_name = media.file_name or media.title
        # 用户上传过自定义封面（poster_source="custom"）时，刮削不覆盖封面；
        # 刮削来的封面在重刮时允许刷新。NULL = 旧数据，按"非自定义"处理。
        keep_custom_poster = media.poster_source == "custom"

    # --- AV mode: route to the JavBus scraper ---
    if scrape_mode == ScrapeMode.AV:
        return await _scrape_av(media_id, source_name, keep_custom_poster=keep_custom_poster)

    # --- TMDB mode (MOVIE / TV / CUSTOM) ---
    kind = _scrape_kind(scrape_mode)
    if cfg is None:
        cfg = await _load_tmdb_config_from_db()
    if not cfg.api_key:
        # Allow scraping when a configured source carries its own API key,
        # even if the global tmdb_api_key is empty.
        configured = await load_scrape_sources(kind)
        if not any(s.kind == "tmdb" and s.api_key for s in configured):
            raise TMDBConfigError("未配置 TMDB API Key（请在设置中填写并保存）")

    if query_override:
        # AI-assisted rescrape: use the AI-suggested title/year directly,
        # bypassing filename parsing and episode/dir fallback. This lets
        # the AI recover from filenames the regex parser misreads.
        query = query_override
        year = year_override
        season_number = None
        episode_number = None
    else:
        query, year, season_number, episode_number = parse_filename(source_name)

        # --- Parent directory fallback for TV episodes ---
        # When the filename is just an episode marker (e.g. "第1集.mp4"),
        # parse_filename returns the marker as the title. Fall back to the
        # parent directory name for a meaningful TMDB search query.
        if kind == "tv" and episode_number is not None:
            if _is_episode_marker_title(query):
                dir_title, dir_season = _parse_parent_dir_for_title(media.file_path)
                query = dir_title
                # Always prefer directory season over the default (season=1
                # is set by parse_filename for seasonless episodes).
                if dir_season is not None:
                    season_number = dir_season

    if not query:
        return ScrapeResult(matched=False, message="无法从文件名解析标题")

    # --- Fallback chain: configured scrape_sources[kind] first, else TMDB default ---
    # Isolation: movie/tv chains only accept kind="tmdb" sources (adult html
    # sources configured under av never leak into the movie/tv chain).
    chain: list[tuple[TMDBConfig, str]] = [(cfg, "TMDB")]
    configured = await load_scrape_sources(kind)
    if configured:
        tmdb_chain = [
            (_source_to_tmdb_config(s, cfg), s.name)
            for s in configured
            if s.kind == "tmdb"
        ]
        if tmdb_chain:
            chain = tmdb_chain

    async with httpx.AsyncClient(timeout=30, proxy=await get_proxy_url()) as client:
        hit = None
        for cfg_i, src_label in chain:
            try:
                hit = await _tmdb_search(client, cfg_i, kind, query, year)
                # Retry without the year constraint if nothing matched
                if not hit and year:
                    hit = await _tmdb_search(client, cfg_i, kind, query, None)
                # Fallback: strip trailing numbers (e.g. "剧场版01" → "剧场版")
                # and re-search without the edition number suffix.
                if not hit:
                    stripped = re.sub(r"\s*\d{1,3}$", "", query).strip()
                    if stripped and stripped != query:
                        hit = await _tmdb_search(client, cfg_i, kind, stripped, year)
                        if not hit and year:
                            hit = await _tmdb_search(client, cfg_i, kind, stripped, None)
                if hit:
                    cfg = cfg_i  # subsequent detail/credits/poster use this source
                    break
            except httpx.HTTPError:
                continue  # source unreachable / errored -> try next in chain
        if not hit:
            names = " → ".join(label for _, label in chain)
            return ScrapeResult(matched=False, message=f"所有数据源均未找到匹配：{query}（{names}）")

        tmdb_id = hit.get("id")
        detail = {}
        try:
            detail = await _tmdb_detail(client, cfg, kind, tmdb_id)
        except httpx.HTTPError:
            detail = {}

        if kind == "movie":
            new_title = detail.get("title") or hit.get("title") or query
            release = detail.get("release_date") or hit.get("release_date") or ""
        else:
            new_title = detail.get("name") or hit.get("name") or query
            release = detail.get("first_air_date") or hit.get("first_air_date") or ""
        overview = detail.get("overview") or hit.get("overview") or None
        poster_rel = detail.get("poster_path") or hit.get("poster_path") or ""
        genres = detail.get("genres") or []
        genre_names = [g["name"] for g in genres if g.get("name")]

        # --- Build scrape_data: rich detail from TMDB for the detail page ---
        scrape_data: dict = {}
        # Common fields (movie + tv)
        scrape_data["tagline"] = detail.get("tagline") or None
        scrape_data["tmdb_rating"] = detail.get("vote_average")
        scrape_data["tmdb_vote_count"] = detail.get("vote_count")
        scrape_data["tmdb_id"] = tmdb_id
        scrape_data["original_title"] = (
            detail.get("original_title") or detail.get("original_name")
        )
        scrape_data["original_language"] = detail.get("original_language")
        scrape_data["status"] = detail.get("status")
        scrape_data["homepage"] = detail.get("homepage") or None
        scrape_data["imdb_id"] = detail.get("imdb_id")
        # TMDB backdrop (movie/tv only): used as the detail-page hero atmosphere.
        scrape_data["backdrop_path"] = (
            detail.get("backdrop_path") or hit.get("backdrop_path") or None
        )
        scrape_data["genres"] = genre_names

        # Production info
        countries = detail.get("production_countries") or []
        scrape_data["production_countries"] = [
            c.get("name") for c in countries if c.get("name")
        ]
        companies = detail.get("production_companies") or []
        scrape_data["production_companies"] = [
            c.get("name") for c in companies if c.get("name")
        ]

        # Spoken languages
        spoken = detail.get("spoken_languages") or []
        scrape_data["spoken_languages"] = [
            s.get("english_name") or s.get("name")
            for s in spoken if s.get("english_name") or s.get("name")
        ]

        if kind == "movie":
            scrape_data["runtime_minutes"] = detail.get("runtime")
            scrape_data["budget"] = detail.get("budget")
            scrape_data["revenue"] = detail.get("revenue")
            scrape_data["belongs_to_collection"] = (
                detail.get("belongs_to_collection", {}).get("name")
                if detail.get("belongs_to_collection")
                else None
            )
        else:
            scrape_data["episode_run_time"] = detail.get("episode_run_time")
            scrape_data["number_of_seasons"] = detail.get("number_of_seasons")
            scrape_data["number_of_episodes"] = detail.get("number_of_episodes")
            scrape_data["in_production"] = detail.get("in_production")
            networks = detail.get("networks") or []
            scrape_data["networks"] = [
                n.get("name") for n in networks if n.get("name")
            ]
            creators = detail.get("created_by") or []
            scrape_data["created_by"] = [
                c.get("name") for c in creators if c.get("name")
            ]

        # Fetch credits (cast + crew) — top 15 cast + key crew
        # Store richer cast data (order, popularity, profile_path) for smart
        # tag filtering: only notable actors become tags, but all are kept in
        # scrape_data for the detail page to display the full cast list.
        try:
            credits = await _tmdb_credits(client, cfg, kind, tmdb_id)
            cast_list = credits.get("cast") or []
            scrape_data["cast"] = [
                {
                    "name": c.get("name"),
                    "character": c.get("character"),
                    "order": c.get("order"),
                    "popularity": c.get("popularity"),
                    "profile_path": c.get("profile_path"),
                }
                for c in cast_list[:15]
                if c.get("name")
            ]
            crew_list = credits.get("crew") or []
            directors = [
                c.get("name") for c in crew_list
                if c.get("job") == "Director" and c.get("name")
            ]
            writers = [
                c.get("name") for c in crew_list
                if c.get("job") in ("Writer", "Screenplay") and c.get("name")
            ]
            scrape_data["directors"] = directors[:5]
            scrape_data["writers"] = list(dict.fromkeys(writers))[:5]  # dedup
        except httpx.HTTPError:
            scrape_data["cast"] = []
            scrape_data["directors"] = []
            scrape_data["writers"] = []

        new_year: int | None = None
        if release[:4].isdigit():
            new_year = int(release[:4])
        elif year:
            new_year = year

        # For TV shows, defer poster download until after Series is resolved,
        # so the poster filename uses the series ID (shared across episodes).
        # 用户上传过封面（poster_source=custom）时跳过下载，保留自定义封面。
        local_poster = None
        if kind != "tv" and not keep_custom_poster:
            try:
                local_poster = await _download_poster(client, cfg, poster_rel, media_id)
            except httpx.HTTPError:
                local_poster = None

    # Persist
    genre_count = 0
    async with async_session() as session:
        media = await session.get(Media, media_id)
        if not media:
            return ScrapeResult(matched=False, message="media not found")
        media.title = new_title
        if new_year:
            media.year = new_year
        if overview:
            media.description = overview
        if local_poster:
            media.poster_path = local_poster
        # Store full release date (YYYY-MM-DD) for display
        if release:
            media.release_date = release
        if season_number is not None:
            media.season_number = season_number
        if episode_number is not None:
            media.episode_number = episode_number
        # Store rich scrape data (tagline, cast, directors, tmdb_rating, etc.)
        if scrape_data:
            media.scrape_data = scrape_data

        # --- Series aggregation for TV shows ---
        # Find or create a Series entity, link this episode to it.
        # This provides tmdb_id-based grouping (upgrades the title-based
        # grouping from the pre-scan aggregator).
        if kind == "tv" and tmdb_id:
            # Find existing Series by tmdb_id + library_id (same-show cache)
            result = await session.execute(
                select(Series).where(
                    Series.tmdb_id == tmdb_id,
                    Series.library_id == media.library_id,
                )
            )
            series = result.scalar_one_or_none()

            if not series and media.series_title:
                # Fallback: find by normalized title (pre-aggregation created it)
                result = await session.execute(
                    select(Series).where(
                        Series.library_id == media.library_id,
                        func.lower(Series.title) == func.lower(media.series_title),
                    )
                )
                series = result.scalar_one_or_none()

            if not series:
                # Create new Series with TMDB metadata
                series = Series(
                    library_id=media.library_id,
                    title=new_title,
                    tmdb_id=tmdb_id,
                    year=new_year,
                    overview=overview,
                    poster_path=None,  # Will be set after flush (need series ID)
                    scrape_data=scrape_data if scrape_data else None,
                    total_seasons=scrape_data.get("number_of_seasons") if scrape_data else None,
                    total_episodes=scrape_data.get("number_of_episodes") if scrape_data else None,
                    episode_count=1,
                )
                session.add(series)
                try:
                    # SAVEPOINT: a concurrent scrape of a sibling episode may
                    # create the same (tmdb_id, library_id) Series first —
                    # roll back only the insert, keep the scrape transaction.
                    async with session.begin_nested():
                        await session.flush()  # Get the ID
                except IntegrityError:
                    result = await session.execute(
                        select(Series).where(
                            Series.tmdb_id == tmdb_id,
                            Series.library_id == media.library_id,
                        )
                    )
                    existing = result.scalar_one_or_none()
                    if existing is None:
                        raise
                    series = existing

                # Download poster with series-specific filename (shared across episodes)
                if poster_rel:
                    try:
                        series_poster = await _download_poster_series(
                            cfg, poster_rel, series.id
                        )
                        series.poster_path = series_poster
                    except httpx.HTTPError:
                        pass
            else:
                # Update existing Series with TMDB metadata (fill missing fields)
                if not series.tmdb_id:
                    series.tmdb_id = tmdb_id
                # Upgrade title to TMDB canonical name
                series.title = new_title
                if new_year and not series.year:
                    series.year = new_year
                if overview and not series.overview:
                    series.overview = overview
                # Download poster if series doesn't have one yet
                if not series.poster_path and poster_rel:
                    try:
                        series_poster = await _download_poster_series(
                            cfg, poster_rel, series.id
                        )
                        series.poster_path = series_poster
                    except httpx.HTTPError:
                        pass
                if scrape_data and not series.scrape_data:
                    series.scrape_data = scrape_data
                if not series.total_seasons and scrape_data:
                    series.total_seasons = scrape_data.get("number_of_seasons")
                if not series.total_episodes and scrape_data:
                    series.total_episodes = scrape_data.get("number_of_episodes")
                # Refresh episode count
                result = await session.execute(
                    select(func.count(Media.id)).where(
                        Media.series_id == series.id,
                        Media.is_deleted == False,  # noqa: E712
                    )
                )
                series.episode_count = result.scalar() or 0

            # Link media to Series and use shared poster
            # （用户上传过封面则不套用系列共享封面）
            media.series_id = series.id
            media.series_title = series.title
            if series.poster_path and not keep_custom_poster:
                media.poster_path = series.poster_path

        await session.commit()

        # Sync TMDB metadata as tags: genres + actors + collection
        tag_specs: list[tuple[str, str]] = []
        # Genres → "genre" type
        for g in genre_names:
            tag_specs.append((g, "genre"))
        # Top cast → "actor" type — smart filter: only notable actors become tags
        # Criteria (any one suffices):
        #   - order <= 3  (main cast, top-billed)
        #   - popularity >= 5.0  (TMDB popularity score, indicates public recognition)
        #   - profile_path is not None  (has a headshot, typically a credited actor)
        # Remaining cast members are still stored in scrape_data["cast"] for the
        # detail page to display the full list — they just don't clutter the tag sidebar.
        for c in scrape_data.get("cast") or []:
            name = c.get("name")
            if not name:
                continue
            order = c.get("order")
            popularity = c.get("popularity") or 0
            has_profile = bool(c.get("profile_path"))
            is_notable = (
                (order is not None and order <= 3)
                or popularity >= 5.0
                or has_profile
            )
            if is_notable:
                tag_specs.append((name, "actor"))
        # Collection → "collection" type
        collection = scrape_data.get("belongs_to_collection")
        if collection:
            tag_specs.append((collection, "collection"))
        genre_count = await _sync_tags_for_media(session, media_id, tag_specs, source="scrape")
        await session.commit()

    logger.info("Scraped media %s -> %s (%s)", media_id, new_title, new_year)
    return ScrapeResult(
        matched=True,
        title=new_title,
        year=new_year,
        overview=overview,
        poster_path=local_poster,
        genre_count=genre_count,
        season_number=season_number,
        episode_number=episode_number,
        message="ok",
    )


async def scrape_media_batch(
    library_id: int | None = None, task_id: int | None = None,
    re_scrape: bool = False,
) -> int:
    """Scrape multiple media files. Called by TaskManager as a worker.

    Processes media whose library has scrape_mode != NONE. Routes AV-mode
    libraries to the JavBus scraper, others to TMDB. Fault tolerant:
    individual failures are logged and skipped. Returns the matched count.

    When re_scrape is False (default), skips media that already have a
    poster_path, avoiding redundant API calls.
    """
    from app.tasks.manager import task_manager

    # Load TMDB config — but only required for non-AV libraries
    cfg = await _load_tmdb_config_from_db()

    async with async_session() as session:
        query = select(
            Media.id, Media.title, Media.file_name, MediaLibrary.scrape_mode
        ).join(
            MediaLibrary, Media.library_id == MediaLibrary.id
        ).where(MediaLibrary.scrape_mode != ScrapeMode.NONE)
        # Never scrape recycle-bin items; honor the user's metadata-ignore
        # unless they explicitly asked for a re-scrape.
        query = query.where(Media.is_deleted == False)  # noqa: E712
        if not re_scrape:
            query = query.where(
                Media.metadata_ignored == False,  # noqa: E712
                Media.poster_path.is_(None),
            )
        if library_id is not None:
            query = query.where(Media.library_id == library_id)
        result = await session.execute(query)
        rows = result.fetchall()

    # Check if any non-AV items exist that need TMDB config
    has_tmdb_items = any(
        row[3] not in (ScrapeMode.AV, ScrapeMode.NONE) for row in rows
    )
    if has_tmdb_items and not cfg.api_key:
        raise TMDBConfigError("未配置 TMDB API Key（请在设置中填写并保存）")

    total = len(rows)
    matched = 0
    for i, (mid, title, file_name, scrape_mode) in enumerate(rows):
        # Surface the media being scraped + its source (TMDB / JavBus) so the
        # task drawer can show "正在刮削：《标题》· TMDB".
        source_label = "JavBus" if scrape_mode == ScrapeMode.AV else "TMDB"
        display_title = title or file_name or f"媒体 #{mid}"
        if task_id:
            await task_manager.update_progress(
                task_id, current=i + 1, total=total,
                subtitle=f"{display_title} · {source_label}",
            )
        try:
            # scrape_media internally routes AV vs TMDB
            res = await scrape_media(mid, cfg if has_tmdb_items else None)
            if res.matched:
                matched += 1
        except (TMDBConfigError, httpx.HTTPError) as exc:
            logger.warning("Scrape failed for media %s: %s", mid, exc)

    return matched


async def _scrape_av(
    media_id: int,
    file_name: str,
    keep_custom_poster: bool = False,
) -> ScrapeResult:
    """Scrape an AV media item via the configured AV source chain and persist.

    Handles the full flow: parse番号 → fetch source page → extract metadata →
    download poster → persist to DB → sync tags (actresses + genres + studio).
    Falls back to built-in JavBus→JavDB→JavLibrary when no AV source is
    configured in ``scrape_sources.av``.

    ``keep_custom_poster``: 用户上传过封面时 True——跳过封面下载/覆盖。
    """
    from app.services.av_scraper import scrape_av_media

    sources = await load_scrape_sources("av")
    result, av_scrape_data = await scrape_av_media(
        media_id,
        file_name,
        sources=sources or None,
        keep_custom_poster=keep_custom_poster,
    )
    if not result.matched or av_scrape_data is None:
        return result

    genre_count = 0
    async with async_session() as session:
        media = await session.get(Media, media_id)
        if not media:
            return ScrapeResult(matched=False, message="media not found")

        media.title = result.title
        if result.year:
            media.year = result.year
        # 用户上传过封面时不覆盖（scrape_av_media 已跳过下载，此处双保险）
        if result.poster_path and not keep_custom_poster:
            media.poster_path = result.poster_path
        release = av_scrape_data.get("release_date") or ""
        if release and not release.startswith("0000"):
            media.release_date = release
        elif (media.release_date or "").startswith("0000"):
            # 新数据无有效日期时，清掉历史遗留的占位日期 0000-00-00
            media.release_date = None
        media.scrape_data = av_scrape_data
        await session.commit()

        # Sync AV tags using AV-specific tag types (isolated from movie/TV):
        # actresses → av_actress, genres → av_genre, studio → av_studio,
        # series → av_series, director → av_director
        tag_specs: list[tuple[str, str]] = []
        for actress in av_scrape_data.get("actresses") or []:
            tag_specs.append((actress, "av_actress"))
        for genre in av_scrape_data.get("genres") or []:
            tag_specs.append((genre, "av_genre"))
        studio = av_scrape_data.get("studio")
        if studio:
            tag_specs.append((studio, "av_studio"))
        series = av_scrape_data.get("series")
        if series:
            tag_specs.append((series, "av_series"))
        director = av_scrape_data.get("director")
        if director:
            tag_specs.append((director, "av_director"))

        genre_count = await _sync_tags_for_media(
            session, media_id, tag_specs, source="scrape"
        )
        await session.commit()

    logger.info("AV-scraped media %s -> %s", media_id, result.title)
    return ScrapeResult(
        matched=True,
        title=result.title,
        year=result.year,
        overview=None,
        poster_path=result.poster_path,
        genre_count=genre_count,
        message="ok",
    )


async def test_tmdb_connection(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    language: str | None = None,
) -> tuple[bool, str]:
    """Validate a TMDB connection using the given (or saved) credentials.

    Returns (ok, message). Never raises — used by the settings test endpoint.
    """
    # Fill missing overrides from saved DB settings so "save then test" works.
    keys = ["tmdb_api_key", "tmdb_base_url", "tmdb_image_base", "tmdb_language"]
    async with async_session() as session:
        result = await session.execute(select(Setting).where(Setting.key.in_(keys)))
        rows = {s.key: (s.value or "") for s in result.scalars().all()}

    cfg = resolve_tmdb_config(
        api_key=api_key if api_key not in (None, "") else rows.get("tmdb_api_key"),
        base_url=base_url if base_url is not None else rows.get("tmdb_base_url"),
        language=language if language is not None else rows.get("tmdb_language"),
        db_rows=rows,
    )
    if not cfg.api_key:
        return False, "未配置 TMDB API Key（请填写并保存）"

    headers, params = _auth(cfg)
    params = {**params, "query": "matrix", "language": cfg.language}
    try:
        async with httpx.AsyncClient(timeout=20, proxy=await get_proxy_url()) as client:
            resp = await client.get(
                f"{cfg.base_url}/search/movie", headers=headers, params=params
            )
            resp.raise_for_status()
            n = len(resp.json().get("results") or [])
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        hint = {
            401: "API Key 无效或未授权",
            403: "无权限（检查 Key 或账户）",
            404: f"接口地址不存在（检查 Base URL：{cfg.base_url}）",
            429: "请求过于频繁",
        }.get(code, f"HTTP {code}")
        return False, f"TMDB 连接失败（{hint}）"
    except httpx.TimeoutException:
        return False, "连接超时（TMDB 需要可访问外网/代理）"
    except httpx.HTTPError as exc:
        return False, f"网络错误：{exc}"

    return True, f"连接成功（测试检索返回 {n} 条结果，language={cfg.language}）"
