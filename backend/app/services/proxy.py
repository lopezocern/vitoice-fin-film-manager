"""Global HTTP proxy resolution.

Reads proxy_enabled / proxy_host / proxy_port from the settings table and
builds a proxy URL (``http://host:port``). Results are cached briefly so
per-request callers (scrapers, aggregator, AI) don't hammer the DB.

Usage:
    from app.services.proxy import get_proxy_url
    proxy = await get_proxy_url()          # "http://127.0.0.1:7890" or None
    httpx.AsyncClient(proxy=proxy, ...)
    curl_cffi AsyncSession(proxy=proxy, ...)
"""
import logging
import time

from app.database import async_session
from app.models.setting import Setting
from sqlalchemy import select

logger = logging.getLogger("vitoice.proxy")

_CACHE_TTL_S = 30  # re-read settings at most every 30s
_cache: dict = {"url": None, "ts": 0.0}


def invalidate_proxy_cache() -> None:
    """Force the next get_proxy_url() call to re-read settings.

    Called by the settings update endpoint so proxy changes take effect
    immediately instead of waiting for the short TTL cache.
    """
    _cache["ts"] = 0.0


async def get_proxy_url() -> str | None:
    """Return the configured proxy URL, or None when disabled / not configured."""
    now = time.time()
    if now - _cache.get("ts", 0) < _CACHE_TTL_S:
        return _cache["url"]

    enabled = False
    host = ""
    port = "7890"
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Setting.key, Setting.value).where(
                    Setting.key.in_(("proxy_enabled", "proxy_host", "proxy_port"))
                )
            )
            rows = {k: (v or "") for k, v in result.all()}
        enabled = rows.get("proxy_enabled", "false").strip().lower() in ("true", "1", "yes")
        host = rows.get("proxy_host", "").strip()
        port = rows.get("proxy_port", "7890").strip()
    except Exception as exc:  # noqa: BLE001 — never break callers on DB hiccups
        logger.warning("Failed to read proxy settings: %s", exc)
        _cache.update(url=None, ts=now)
        return None

    url: str | None = None
    if enabled and host:
        url = f"http://{host}:{port}" if port else f"http://{host}"
    _cache.update(url=url, ts=now)
    return url


async def test_proxy_connection(host: str, port: str, timeout: float = 8.0) -> tuple[bool, str]:
    """Probe the proxy by fetching a known URL through it. Never raises."""
    import httpx

    proxy_url = f"http://{host}:{port}" if port else f"http://{host}"
    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout) as client:
            resp = await client.get("https://api.themoviedb.org/3", follow_redirects=True)
            return True, f"代理连通 (HTTP {resp.status_code})"
    except Exception as exc:  # noqa: BLE001
        return False, f"代理连接失败: {exc}"
