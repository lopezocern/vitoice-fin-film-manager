"""Setting routes — key-value configuration."""
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.enums import SettingType
from app.models.setting import Setting
from app.schemas.setting import (
    SettingBulkUpdate,
    SettingResponse,
    SettingUpdate,
)


class TestAIRequest(BaseModel):
    """Optional overrides for testing an AI connection.

    When a field is omitted, the value saved in the settings table (or the env
    default) is used. This lets the user test what they typed before saving.
    """

    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None


class TestTMDBRequest(BaseModel):
    """Optional overrides for testing a TMDB connection.

    Omitted fields fall back to saved settings / env defaults, so the user can
    test either what they just typed or what they already saved.
    """

    api_key: str | None = None
    base_url: str | None = None
    language: str | None = None

router = APIRouter(prefix="/settings", tags=["settings"])

# Keys whose values must never be returned in plain text
_SENSITIVE_KEYS = {"ai_api_key", "tmdb_api_key"}


def _mask_value(key: str, value: str | None) -> str | None:
    """Mask sensitive setting values for API responses.

    Returns ``****`` for short values, or ``****<last4>`` for longer ones.
    Non-sensitive keys are returned unchanged.
    """
    if key in _SENSITIVE_KEYS and value:
        if len(value) <= 4:
            return "****"
        return "****" + value[-4:]
    return value


def _is_masked(value: str | None) -> bool:
    """Check if a value is a masked placeholder (starts with ****)."""
    return bool(value) and value.startswith("****")


async def _get_setting_or_404(db: AsyncSession, key: str) -> Setting:
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if not setting:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    return setting


@router.get("", response_model=list[SettingResponse])
async def list_settings(db: AsyncSession = Depends(get_db)):
    """List all settings, grouped by category then key.

    Sensitive keys (ai_api_key, tmdb_api_key) are masked in the response.
    """
    result = await db.execute(
        select(Setting).order_by(Setting.category, Setting.key)
    )
    settings = result.scalars().all()
    # Build Pydantic responses (not SQLAlchemy instances) so masking
    # doesn't get persisted by get_db's commit.
    responses = []
    for s in settings:
        resp = SettingResponse.model_validate(s)
        resp.value = _mask_value(s.key, s.value)
        responses.append(resp)
    return responses


@router.put("", response_model=list[SettingResponse])
async def bulk_update_settings(
    payload: SettingBulkUpdate, db: AsyncSession = Depends(get_db)
):
    """Bulk update settings — creates settings that don't exist yet.

    Skips sensitive keys whose value is a masked placeholder (****xxxx),
    so the frontend can submit the mask unchanged without overwriting
    the stored secret.
    """
    updated: list[Setting] = []
    for item in payload.settings:
        # Skip masked sensitive values — frontend sends mask when unchanged
        if item.key in _SENSITIVE_KEYS and _is_masked(item.value):
            continue
        result = await db.execute(select(Setting).where(Setting.key == item.key))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = item.value
        else:
            setting = Setting(key=item.key, value=item.value)
            db.add(setting)
        # 代理配置变更立即生效（清除 30s TTL 缓存）
        if item.key in ("proxy_enabled", "proxy_host", "proxy_port"):
            from app.services.proxy import invalidate_proxy_cache

            invalidate_proxy_cache()
        updated.append(setting)

    await db.flush()
    responses = []
    for s in updated:
        await db.refresh(s)
        resp = SettingResponse.model_validate(s)
        resp.value = _mask_value(s.key, s.value)
        responses.append(resp)
    return responses


# =====================================================================
# Scrape source chains (movie / tv / av)
#
# Stored under the 'scrape_sources' setting as a JSON dict grouped by
# content kind. Isolation contract: the av group only accepts html
# (adult-site) sources; movie/tv groups only accept tmdb sources.
# =====================================================================

_ALLOWED_SOURCE_KINDS = ("movie", "tv", "av")
_ALLOWED_SOURCE_TYPES = ("tmdb", "html")
# Must cover every parser in av_scraper._AV_PARSERS (incl. the values
# _infer_av_parser can return), otherwise saving a source the scraper
# itself infers gets rejected with 422.
_ALLOWED_PARSERS = ("", "javbus", "javdb", "javlibrary", "3xplanet")


class ScrapeSourcesPayload(BaseModel):
    sources: dict[str, list[dict]]


class TestSourceRequest(BaseModel):
    kind: str
    source: dict


class TestProxyRequest(BaseModel):
    host: str | None = None
    port: str | None = None


def _mask_api_key(value: str) -> str:
    if not value:
        return ""
    return "****" + value[-4:] if len(value) > 4 else "****"


def _validate_sources_payload(data: dict) -> str | None:
    """Validate a scrape_sources payload. Returns an error message or None."""
    if not isinstance(data, dict):
        return "数据格式错误：应为 JSON 对象"
    for kind in _ALLOWED_SOURCE_KINDS:
        items = data.get(kind, [])
        if not isinstance(items, list):
            return f"分组 {kind} 应为数组"
        for it in items:
            if not isinstance(it, dict):
                return f"分组 {kind} 中存在非法源（应为对象）"
            if it.get("kind") not in _ALLOWED_SOURCE_TYPES:
                return f"源 {it.get('name', '?')} 的 kind 非法"
            # Group-level isolation: av only takes html (adult-site) sources;
            # movie/tv only take tmdb sources. Cross-group entries are rejected.
            if kind == "av" and it.get("kind") != "html":
                return f"限制内容分组仅支持 html 类型源：{it.get('name', '?')}"
            if kind != "av" and it.get("kind") != "tmdb":
                return f"{kind} 分组仅支持 tmdb 类型源：{it.get('name', '?')}"
            if not str(it.get("base_url") or "").strip():
                return f"源 {it.get('name', '?')} 缺少 base_url"
            parser = str(it.get("parser") or "").strip().lower()
            if parser not in _ALLOWED_PARSERS:
                return f"源 {it.get('name', '?')} 的 parser 非法"
    return None


def _mask_sources(data: dict) -> dict:
    """Return a deep-copied view with api_key values masked."""
    import copy

    view = copy.deepcopy(data)
    for kind in _ALLOWED_SOURCE_KINDS:
        for it in view.get(kind) or []:
            if isinstance(it, dict) and it.get("api_key"):
                it["api_key"] = _mask_api_key(str(it["api_key"]))
    return view


@router.get("/scrape-sources")
async def get_scrape_sources(db: AsyncSession = Depends(get_db)):
    """Get the configured scrape source chains (movie/tv/av).

    api_key values are masked (mirrors the global tmdb_api_key policy).
    Empty groups mean the built-in defaults apply.

    Isolation: when ``show_restricted`` is OFF, the av group is returned
    empty so adult source configs are never exposed.
    """
    result = await db.execute(select(Setting).where(Setting.key == "scrape_sources"))
    setting = result.scalar_one_or_none()
    if not setting or not setting.value:
        return {"movie": [], "tv": [], "av": []}
    try:
        data = json.loads(setting.value)
    except json.JSONDecodeError:
        return {"movie": [], "tv": [], "av": []}
    if not isinstance(data, dict):
        return {"movie": [], "tv": [], "av": []}
    data = _mask_sources(data)
    # Adult-content isolation: hide the av group while show_restricted is off.
    show_result = await db.execute(
        select(Setting.value).where(Setting.key == "show_restricted")
    )
    show = (show_result.scalar() or "").strip().lower() in ("true", "1", "yes")
    if not show:
        data["av"] = []
    return data


@router.put("/scrape-sources")
async def put_scrape_sources(
    payload: ScrapeSourcesPayload, db: AsyncSession = Depends(get_db)
):
    """Validate and persist the scrape source chains.

    Masked api_key placeholders (****) are restored from the stored value
    so an untouched key survives a full-payload save from the UI.
    """
    data = payload.sources
    err = _validate_sources_payload(data)
    if err:
        raise HTTPException(status_code=422, detail=err)

    result = await db.execute(select(Setting).where(Setting.key == "scrape_sources"))
    setting = result.scalar_one_or_none()
    stored: dict = {"movie": [], "tv": [], "av": []}
    if setting and setting.value:
        try:
            old = json.loads(setting.value)
            if isinstance(old, dict):
                stored = old
        except json.JSONDecodeError:
            pass

    # Adult-content isolation: while show_restricted is OFF, the av group is
    # read-only — keep the stored value so a hidden UI cannot wipe it.
    show_result = await db.execute(
        select(Setting.value).where(Setting.key == "show_restricted")
    )
    show = (show_result.scalar() or "").strip().lower() in ("true", "1", "yes")
    if not show:
        data["av"] = stored.get("av") or []

    # Restore masked api_key placeholders from the stored values.
    for kind in _ALLOWED_SOURCE_KINDS:
        old_items = {
            str(it.get("name")): it
            for it in (stored.get(kind) or [])
            if isinstance(it, dict)
        }
        for it in data.get(kind) or []:
            if it.get("api_key") and _is_masked(str(it["api_key"])):
                name = str(it.get("name"))
                it["api_key"] = old_items.get(name, {}).get("api_key") or ""

    if not setting:
        setting = Setting(
            key="scrape_sources",
            value="",
            type=SettingType.JSON,
            category="scrape",
        )
        db.add(setting)
    setting.value = json.dumps(data, ensure_ascii=False)
    await db.flush()
    await db.refresh(setting)
    return _mask_sources(json.loads(setting.value))


@router.post("/test-proxy")
async def test_proxy(
    payload: TestProxyRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Test connectivity through the configured (or given) HTTP proxy."""
    from app.services.proxy import test_proxy_connection

    payload = payload or TestProxyRequest()
    # Fill missing fields from saved settings
    result = await db.execute(
        select(Setting).where(Setting.key.in_(("proxy_host", "proxy_port")))
    )
    rows = {s.key: (s.value or "") for s in result.scalars().all()}
    host = (payload.host or "").strip() or rows.get("proxy_host", "").strip()
    port = (payload.port or "").strip() or rows.get("proxy_port", "7890").strip()
    if not host:
        return {"ok": False, "message": "未配置代理地址"}

    ok, message = await test_proxy_connection(host, port)
    return {"ok": ok, "message": message}


@router.post("/test-source")
async def test_source(
    payload: TestSourceRequest, db: AsyncSession = Depends(get_db)
):
    """Test connectivity for a single scrape source.

    The source must belong to the given kind group — av sources are
    isolated from movie/tv sources (adult vs normal content isolation).
    """
    from app.services.scraper import ScrapeSource, test_scrape_source

    kind = payload.kind
    if kind not in _ALLOWED_SOURCE_KINDS:
        raise HTTPException(status_code=422, detail=f"kind 非法：{kind}")
    # ISOLATION: av-source connectivity tests are gated behind
    # show_restricted — with restricted content hidden there is no
    # legitimate surface that would ever need this check.
    if kind == "av":
        restricted_on = await db.execute(
            select(Setting.value).where(Setting.key == "show_restricted")
        )
        raw = (restricted_on.scalar() or "").strip().lower()
        if raw not in ("true", "1", "yes"):
            raise HTTPException(status_code=403, detail="受限内容已隐藏")
    src_kind = payload.source.get("kind")
    # Isolation: av group only accepts html (adult-site) sources; the
    # movie/tv groups only accept tmdb sources.
    if kind == "av":
        if src_kind != "html":
            raise HTTPException(status_code=422, detail="限制内容分组仅支持 html 类型源")
    else:
        if src_kind != "tmdb":
            raise HTTPException(status_code=422, detail="movie/tv 分组仅支持 tmdb 类型源")

    api_key = str(payload.source.get("api_key") or "").strip()
    if api_key and _is_masked(api_key):
        api_key = ""  # masked placeholder -> inherit global tmdb_api_key

    src = ScrapeSource(
        name=str(payload.source.get("name") or "测试源"),
        kind=src_kind or "tmdb",
        base_url=str(payload.source.get("base_url") or "").strip(),
        image_base=str(payload.source.get("image_base") or "").strip(),
        api_key=api_key,
        language=str(payload.source.get("language") or "").strip(),
        timeout=int(payload.source.get("timeout") or 20),
        parser=str(payload.source.get("parser") or "").strip().lower(),
    )
    if not src.base_url:
        raise HTTPException(status_code=422, detail="缺少 base_url")
    if src.parser not in _ALLOWED_PARSERS:
        raise HTTPException(status_code=422, detail="parser 非法")

    ok, message = await test_scrape_source(src, kind)
    return {"ok": ok, "message": message}


# NOTE: must be declared BEFORE the /{key} catch-all below, or FastAPI would
# match "asset-stats" as a literal key lookup.
@router.get("/asset-stats")
async def asset_stats():
    """Report orphan thumbnail/poster files (media id no longer in DB)."""
    import asyncio
    return await asyncio.to_thread(_scan_orphan_assets)


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(key: str, db: AsyncSession = Depends(get_db)):
    """Get a single setting by key. Sensitive values are masked."""
    setting = await _get_setting_or_404(db, key)
    resp = SettingResponse.model_validate(setting)
    resp.value = _mask_value(setting.key, setting.value)
    return resp


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str, payload: SettingUpdate, db: AsyncSession = Depends(get_db)
):
    """Update a single setting by key.

    If the key is sensitive and the payload value is a masked placeholder,
    the value is left unchanged (frontend sends mask when user didn't edit).
    """
    setting = await _get_setting_or_404(db, key)
    update_data = payload.model_dump(exclude_unset=True)
    # Skip masked sensitive values
    if key in _SENSITIVE_KEYS and "value" in update_data:
        if _is_masked(update_data["value"]):
            del update_data["value"]
    for field, value in update_data.items():
        setattr(setting, field, value)
    await db.flush()
    await db.refresh(setting)
    resp = SettingResponse.model_validate(setting)
    resp.value = _mask_value(setting.key, setting.value)
    return resp


@router.post("/test-ai")
async def test_ai_connection(
    payload: TestAIRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Test the AI provider connection using the values the user typed.

    Priority: request-body overrides -> saved settings (DB) -> env defaults.
    Returns ok=false with a specific reason on failure; ok=true when the
    provider responds. Never raises on provider errors so the frontend can
    show a friendly message.
    """
    from app.services.ai_tagger import call_ai_api_checked, resolve_ai_config

    payload = payload or TestAIRequest()

    # Fetch saved AI settings from DB so resolve_ai_config can apply
    # defaults for fields the user left blank.
    keys = ["ai_base_url", "ai_api_key", "ai_model"]
    result = await db.execute(select(Setting).where(Setting.key.in_(keys)))
    db_rows = {s.key: (s.value or "") for s in result.scalars().all()}

    # Resolve once with payload overrides + DB defaults → get correct base_url/etc.
    # CRITICAL: when the frontend sends a masked api_key (****xxxx, which
    # happens after page reload since the GET /settings endpoint masks
    # sensitive values), we must fall back to the DB-stored real key.
    # Otherwise the masked string gets sent to the AI provider as the actual
    # credential, causing "Authentication Fails" errors.
    masked_api_key = payload.api_key is not None and _is_masked(payload.api_key)
    cfg = resolve_ai_config(
        base_url=payload.base_url,
        api_key=None if masked_api_key else (payload.api_key if payload.api_key not in (None, "") else None),
        model=payload.model,
        db_rows=db_rows,
    )

    ok, message, _ = await call_ai_api_checked(
        "ping",
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        model=cfg.model,
    )
    return {"ok": ok, "message": message}


@router.post("/test-tmdb")
async def test_tmdb(
    payload: TestTMDBRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Test the TMDB connection using the values the user typed or saved.

    Priority: request-body overrides -> saved settings (DB) -> env defaults.
    Never raises on provider errors so the frontend can show a friendly message.
    """
    from app.services.scraper import test_tmdb_connection

    payload = payload or TestTMDBRequest()
    # CRITICAL: when the frontend sends a masked api_key (****xxxx), fall back
    # to the DB-stored real key — same fix as test-ai above.
    masked_key = payload.api_key is not None and _is_masked(payload.api_key)
    ok, message = await test_tmdb_connection(
        api_key=None if masked_key else payload.api_key,
        base_url=payload.base_url,
        language=payload.language,
    )
    return {"ok": ok, "message": message}


# =====================================================================
# Thumbnail / poster orphan cleanup
#
# Media records may be permanently deleted while their thumbnail/poster
# files remain on disk (thumbnails/{id}.jpg, posters/{id}.jpg). These
# endpoints report and delete such orphan files. Only files inside the
# managed asset directories are ever touched (S1 path whitelist).
# =====================================================================

def _collect_known_media_ids() -> set[int]:
    """Collect every media id in the DB (including soft-deleted rows)."""
    import sqlite3
    from app.config import settings as _cfg

    db_path = str(_cfg.database_url).replace("sqlite+aiosqlite:///", "")
    try:
        conn = sqlite3.connect(db_path)
        ids = {r[0] for r in conn.execute("SELECT id FROM media").fetchall()}
        conn.close()
        return ids
    except Exception:  # noqa: BLE001 — DB locked/unavailable: treat as empty
        return set()


def _scan_orphan_assets() -> dict:
    """Scan thumbnail/poster dirs for files whose media id no longer exists.

    Returns per-kind {count, bytes, sample[:10]}.
    """
    from app.config import settings as _cfg

    known_ids = _collect_known_media_ids()
    result: dict[str, dict] = {}
    for kind, folder in (
        ("thumbnails", _cfg.thumbnail_dir),
        ("posters", _cfg.poster_dir),
    ):
        count = 0
        total_bytes = 0
        sample: list[str] = []
        try:
            for p in folder.glob("*.jpg"):
                try:
                    media_id = int(p.stem)
                except ValueError:
                    continue
                if media_id in known_ids:
                    continue
                try:
                    sz = p.stat().st_size
                except OSError:
                    sz = 0
                count += 1
                total_bytes += sz
                if len(sample) < 10:
                    sample.append(p.name)
        except OSError:
            pass
        result[kind] = {"count": count, "bytes": total_bytes, "sample": sample}
    return result


def _asset_roots():
    """Resolved thumbnail/poster dirs (S1 whitelist for deletion)."""
    from app.config import settings as _cfg

    return (_cfg.thumbnail_dir.resolve(), _cfg.poster_dir.resolve())


@router.post("/clean-assets")
async def clean_assets():
    """Delete orphan thumbnail/poster files. Returns freed count + bytes."""
    import asyncio

    stats = await asyncio.to_thread(_scan_orphan_assets)
    known_ids = await asyncio.to_thread(_collect_known_media_ids)
    roots = _asset_roots()

    from app.config import settings as _cfg

    freed_count = 0
    freed_bytes = 0
    for folder in (_cfg.thumbnail_dir, _cfg.poster_dir):
        try:
            for p in folder.glob("*.jpg"):
                try:
                    media_id = int(p.stem)
                except ValueError:
                    continue
                if media_id in known_ids:
                    continue
                # S1 whitelist: only ever delete inside managed dirs
                try:
                    resolved = p.resolve()
                except (OSError, RuntimeError):
                    continue
                if not any(
                    resolved == root or root in resolved.parents for root in roots
                ):
                    continue
                try:
                    sz = p.stat().st_size
                    p.unlink()
                    freed_count += 1
                    freed_bytes += sz
                except OSError:
                    continue
        except OSError:
            pass

    # Re-scan to report what remains
    remaining = await asyncio.to_thread(_scan_orphan_assets)
    return {
        "removed_count": freed_count,
        "freed_bytes": freed_bytes,
        "remaining": {
            k: {"count": v["count"], "bytes": v["bytes"]} for k, v in remaining.items()
        },
    }
