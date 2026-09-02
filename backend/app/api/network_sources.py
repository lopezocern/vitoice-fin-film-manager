"""Network source resolution — adult aggregator (javgg-style) only.

ISOLATION: this module exclusively serves adult aggregator sources. It is
gated by the `network_allow_adult` master switch (403 when off) and its
frontend entry is additionally hidden while `show_restricted` is off. It
never writes to media_urls / media_import — resolution results are returned
to the caller, who decides whether to add them through the normal network
source APIs.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.media import Media, MediaUrl
from app.models.enums import UrlRole
from app.models.setting import Setting
from app.services.media_access import get_accessible_media

router = APIRouter(prefix="/network", tags=["network"])


class AdultResolveRequest(BaseModel):
    fancode: str
    base_url: str | None = None  # optional override of the configured aggregator root


class AdultRefreshRequest(BaseModel):
    media_id: int
    fancode: str
    base_url: str | None = None


_ADULT_SERVERS = ("vidhide", "turboplay", "streamwish")


async def _adult_enabled(db: AsyncSession) -> bool:
    result = await db.execute(
        select(Setting.value).where(Setting.key == "network_allow_adult")
    )
    return (result.scalar() or "").strip().lower() in ("true", "1", "yes")


async def _adult_base_url(db: AsyncSession, override: str | None) -> str:
    base = (override or "").strip()
    if not base:
        result = await db.execute(
            select(Setting.value).where(Setting.key == "network_adult_base_url")
        )
        base = (result.scalar() or "").strip()
    if base and not (base.startswith("http://") or base.startswith("https://")):
        raise HTTPException(status_code=422, detail="聚合站地址必须以 http:// 或 https:// 开头")
    return base or "https://javgg.net"


@router.post("/adult-resolve")
async def adult_resolve(payload: AdultResolveRequest):
    """Resolve an adult aggregator fancode into playable stream URLs.

    Gated by `network_allow_adult` — returns 403 while the feature is off.
    Uses the configured `network_adult_base_url` unless `base_url` is given.
    Returns {status, message, fancode, results[]} (see adult_source.resolve).

    The DB connection is released before the network resolution — resolving
    can take 10-20s and must not hold the pool's only connections, which
    would starve other requests.
    """
    from app.services.adult_source import resolve

    # Read switch + aggregator root in a short-lived session, then release.
    async with async_session() as db:
        if not await _adult_enabled(db):
            raise HTTPException(status_code=403, detail="成人网络源功能未开启（设置 → 内容管理）")
        base_url = await _adult_base_url(db, payload.base_url)

    return await resolve(payload.fancode, base_url=base_url)


@router.post("/adult-refresh")
async def adult_refresh(payload: AdultRefreshRequest):
    """Re-resolve an adult media's sources and sync them onto its MediaUrl rows.

    For each resolved server (vidhide/turboplay/streamwish):
      - an existing source URL with a matching platform is updated in place
        (new signed URL, is_expired cleared);
      - a missing platform gets a NEW source URL added.
    This gives the player a multi-source switch list and refreshes the
    36h-expiring signed URLs in one click.

    ISOLATION: gated by network_allow_adult (403) and only ever touches
    adult-platform URLs on the target media.

    Connection hygiene: DB is used only in short phases (read config/rows →
    release → network resolve → release → write), so a 10-20s resolution
    never holds the pool's connections and starves other requests.
    """
    from app.services.adult_source import resolve

    # Phase 1 — read switch, aggregator root and existing source rows (pure
    # data only), then release the connection.
    async with async_session() as db:
        if not await _adult_enabled(db):
            raise HTTPException(status_code=403, detail="成人网络源功能未开启（设置 → 内容管理）")
        base_url = await _adult_base_url(db, payload.base_url)

        result = await db.execute(
            select(Media)
            .where(Media.id == payload.media_id)
            .options(selectinload(Media.urls))
        )
        media = result.scalar_one_or_none()
        if not media:
            raise HTTPException(status_code=404, detail="媒体不存在")
        media_id = media.id

        # Existing source URLs: platform -> url_id. Aggregator PAGE links
        # (javgg article URLs imported by the user) are collected separately
        # to be demoted to reference role — they stay visible in 资源链接 as
        # the source-of-truth page while only playable streams remain in the
        # player's source switcher.
        #
        # Legacy dedup: older versions of the "从聚合站解析" flow appended a
        # fresh signed URL per click, so the same platform could accumulate
        # multiple source rows. We keep the LATEST row per platform and mark
        # older ones for removal (done in phase 3) — one refresh converges
        # historical duplicates.
        existing: dict[str, int] = {}
        dup_source_ids: list[int] = []
        page_url_ids: list[int] = []
        for u in media.urls:
            if u.url_role != UrlRole.SOURCE:
                continue
            lower = (u.url or "").lower()
            if "javgg" in lower or "/jav/" in lower:
                page_url_ids.append(u.id)
                continue
            if u.platform:
                p = u.platform.strip().lower()
                prev = existing.get(p)
                if prev is not None:
                    dup_source_ids.append(prev)
                existing[p] = u.id

    # Phase 2 — network resolution (no DB connection held).
    refresh_result = await resolve(payload.fancode, base_url=base_url)
    if refresh_result.get("status") != "ok":
        return {"updated": 0, "added": 0, "refresh": refresh_result}

    # Phase 3 — write back in a fresh session.
    demoted_pages = 0
    updated = 0
    added = 0
    removed = 0
    async with async_session() as db:
        # Gate: the adult-source resolver must refuse restricted / soft-deleted
        # media. Without this, turning the restricted switch off still allowed
        # resolving (and writing back) network sources by calling this
        # endpoint directly.
        media_row = await get_accessible_media(db, media_id)

        if page_url_ids:
            rows = (
                await db.execute(select(MediaUrl).where(MediaUrl.id.in_(page_url_ids)))
            ).scalars().all()
            for r in rows:
                if r.url_role == UrlRole.SOURCE:
                    r.url_role = UrlRole.REFERENCE
                    demoted_pages += 1

        # 收敛历史重复：同 platform 只保留最新一条 source，其余删除。
        # 删除可能清空最后一条 SOURCE —— 必须重算 media_type（否则记录
        # 会停留在 both/network 却没有任何可播源，误入"网络媒体"分区）。
        if dup_source_ids:
            rows = (
                await db.execute(select(MediaUrl).where(MediaUrl.id.in_(dup_source_ids)))
            ).scalars().all()
            for r in rows:
                if r.url_role == UrlRole.SOURCE and r.media_id == media_id:
                    await db.delete(r)
                    removed += 1
        record_deleted = False
        if removed and media_row is not None:
            from app.services.media_type import demote_media_type_after_source_removal
            record_deleted = await demote_media_type_after_source_removal(media_row, db)

        for item in refresh_result.get("results", []):
            m3u8 = item.get("m3u8_url")
            if not m3u8:
                continue
            server = (item.get("server") or "").strip().lower()
            if server not in _ADULT_SERVERS:
                continue
            url_id = existing.get(server)
            if url_id is not None:
                row = await db.get(MediaUrl, url_id)
                if row:
                    row.url = m3u8
                    row.is_expired = False
                    updated += 1
            else:
                db.add(
                    MediaUrl(
                        media_id=media_id,
                        url=m3u8,
                        url_role=UrlRole.SOURCE,
                        title=payload.fancode.strip().upper(),
                        platform=server,
                    )
                )
                added += 1

        # 新增 SOURCE 后同步升级类型（LOCAL -> BOTH），与 create 端点语义一致；
        # NETWORK 记录若已因无源被整体删除则跳过。
        if added and not record_deleted and media_row is not None:
            from app.services.media_type import promote_media_type_for_source
            promote_media_type_for_source(media_row)

        await db.flush()
        # 手动会话（async with async_session）不会自动提交——
        # 缺 commit 会导致上面所有更新/新增/删除在会话退出时回滚。
        await db.commit()

    return {
        "updated": updated,
        "added": added,
        "removed": removed,
        "demoted_pages": demoted_pages,
        "refresh": refresh_result,
    }
