"""On-demand renewal of adult network stream sources.

The adult CDNs hand out *signed* stream URLs with a short lifetime (currently
~36h). Once a signed URL expires every request 403s until the user manually
clicks "刷新源" in the UI. This service lets the streaming proxy renew a source
transparently — triggered by ``is_expired`` or a 403 from the CDN.

Isolation: only ever touches SOURCE rows whose platform is one of the adult
hosts, and only while the ``network_allow_adult`` switch is on.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.database import async_session
from app.models.enums import UrlRole
from app.models.media import MediaUrl
from app.models.setting import Setting

logger = logging.getLogger("vitoice.network")

ADULT_SERVERS = ("vidhide", "turboplay", "streamwish", "dood")
DEFAULT_BASE_URL = "https://javgg.net"


async def _read_context(
    media_id: int,
) -> tuple[bool, str, dict[str, int], str | None]:
    """Read the switch, aggregator root, existing source rows and fancode.

    Returns ``(enabled, base_url, {platform: url_id}, fancode)``. Fancode is
    taken from the source row's title, which the refresh endpoint stores as the
    upper-cased fancode.
    """
    async with async_session() as db:
        cfg = {
            k: (v or "").strip()
            for k, v in (
                await db.execute(
                    select(Setting.key, Setting.value).where(
                        Setting.key.in_(
                            ("network_allow_adult", "network_adult_base_url")
                        )
                    )
                )
            ).all()
        }
        rows = (
            await db.execute(
                select(MediaUrl.id, MediaUrl.platform, MediaUrl.title).where(
                    MediaUrl.media_id == media_id,
                    MediaUrl.url_role == UrlRole.SOURCE,
                )
            )
        ).all()

    enabled = cfg.get("network_allow_adult", "").lower() in ("true", "1", "yes")
    base_url = cfg.get("network_adult_base_url") or DEFAULT_BASE_URL
    if not base_url.startswith(("http://", "https://")):
        base_url = DEFAULT_BASE_URL

    existing: dict[str, int] = {}
    fancode: str | None = None
    for url_id, platform, title in rows:
        p = (platform or "").strip().lower()
        if p not in ADULT_SERVERS:
            continue
        existing.setdefault(p, url_id)
        if not fancode and title:
            fancode = title.strip()
    return enabled, base_url, existing, fancode


async def renew_media_sources(media_id: int, platform: str | None = None) -> dict:
    """Re-resolve an adult media's sources and refresh its MediaUrl rows.

    Returns ``{"ok", "fresh": {platform: url}, "fancode", "message"}``. Never
    raises — the streaming path treats any failure as "no renewal available"
    and falls back to the original URL / error.
    """
    plat = (platform or "").strip().lower()
    if platform is not None and plat not in ADULT_SERVERS:
        return {"ok": False, "fresh": {}, "fancode": None, "message": "非成人网络源，跳过续签"}

    try:
        enabled, base_url, existing, fancode = await _read_context(media_id)
    except Exception as exc:  # noqa: BLE001 — renewal must never break playback
        logger.warning("renew: read context failed (media %s): %s", media_id, exc)
        return {"ok": False, "fresh": {}, "fancode": None, "message": "读取媒体源失败"}

    if not enabled:
        return {"ok": False, "fresh": {}, "fancode": fancode, "message": "成人网络源功能未开启"}
    if not existing:
        return {"ok": False, "fresh": {}, "fancode": fancode, "message": "该媒体没有可续签的网络源"}
    if not fancode:
        return {"ok": False, "fresh": {}, "fancode": None, "message": "缺少番号，无法续签"}

    from app.services.adult_source import resolve

    try:
        result = await resolve(fancode, base_url=base_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("renew: resolve failed (%s): %s", fancode, exc)
        return {"ok": False, "fresh": {}, "fancode": fancode, "message": "重新解析失败"}

    if result.get("status") != "ok":
        return {
            "ok": False,
            "fresh": {},
            "fancode": fancode,
            "message": result.get("message") or "重新解析失败",
        }

    fresh: dict[str, str] = {}
    for item in result.get("results", []):
        m3u8 = item.get("m3u8_url")
        srv = (item.get("server") or "").strip().lower()
        if m3u8 and srv in ADULT_SERVERS:
            fresh[srv] = m3u8
    if not fresh:
        return {"ok": False, "fresh": {}, "fancode": fancode, "message": "未解析出可用流地址"}

    try:
        async with async_session() as db:
            for srv, m3u8 in fresh.items():
                url_id = existing.get(srv)
                if url_id is not None:
                    row = await db.get(MediaUrl, url_id)
                    if row is not None and row.media_id == media_id:
                        row.url = m3u8
                        row.is_expired = False
                else:
                    db.add(
                        MediaUrl(
                            media_id=media_id,
                            url=m3u8,
                            url_role=UrlRole.SOURCE,
                            title=fancode.upper(),
                            platform=srv,
                        )
                    )
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("renew: write-back failed (media %s): %s", media_id, exc)
        return {"ok": False, "fresh": fresh, "fancode": fancode, "message": "续签结果写回失败"}

    logger.info("renew: media %s fancode %s refreshed %s", media_id, fancode, list(fresh))
    return {"ok": True, "fresh": fresh, "fancode": fancode, "message": "已续签"}