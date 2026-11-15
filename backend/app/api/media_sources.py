"""自定义在线源的 API：配置、探活、聚合搜索、单条解析。

与 `/network/*` 的分工：
- `/network/*` 是既有的成人站聚合解析（fancode → 播放地址），面向"已入库的媒体"；
- `/sources/*` 是通用的可配置源（苹果 CMS 采集站），面向"搜索 → 在线播放 / 入库"。

两者不共用配置：前者绑定站点实现，后者是用户自填的接口列表。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import media_sources_store as store
from app.services.media_sources import (
    MediaSource,
    validate_source,
    validate_sources,
)

router = APIRouter(prefix="/sources", tags=["sources"])


class SourcePayload(BaseModel):
    id: str | None = None
    name: str
    base_url: str
    kind: str = "cms_vod"
    api_path: str = "api.php/provide/vod"
    enabled: bool = True
    timeout: float = 12.0
    headers: dict[str, str] = Field(default_factory=dict)


class SourcesSavePayload(BaseModel):
    sources: list[SourcePayload] = Field(default_factory=list)


class ProbePayload(BaseModel):
    """探活：既支持已保存的源（id），也支持表单里尚未保存的地址。"""

    id: str | None = None
    name: str = "探活"
    base_url: str | None = None
    kind: str = "cms_vod"
    api_path: str = "api.php/provide/vod"
    timeout: float = 12.0
    headers: dict[str, str] = Field(default_factory=dict)


class ResolvePayload(BaseModel):
    source_id: str
    vod_id: str


def _health_dict(health) -> dict[str, Any]:
    return {
        "fail_streak": health.fail_streak,
        "disabled_until": health.disabled_until,
        "last_ok_at": health.last_ok_at,
        "last_error": health.last_error,
        "latency_ms": health.latency_ms,
        "available": health.is_available(),
    }


@router.get("")
async def list_sources(db: AsyncSession = Depends(get_db)):
    """列出源配置与健康度（前端"源管理"页一次拿全）。"""
    sources = await store.load_sources(db)
    health = await store.load_health(db)
    return {
        "sources": [
            {
                "id": s.id,
                "name": s.name,
                "kind": s.kind,
                "base_url": s.base_url,
                "api_path": s.api_path,
                "enabled": s.enabled,
                "timeout": s.timeout,
                "headers": s.headers,
                "health": _health_dict(health[s.id]) if s.id in health else None,
            }
            for s in sources
        ]
    }


@router.put("")
async def save_sources(payload: SourcesSavePayload, db: AsyncSession = Depends(get_db)):
    """整表覆盖保存。校验失败返回 422 且不落库。"""
    try:
        sources = validate_sources([s.model_dump() for s in payload.sources])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await store.save_sources(db, sources)
    return {"status": "ok", "count": len(sources)}


@router.post("/test")
async def test_source(payload: ProbePayload, db: AsyncSession = Depends(get_db)):
    """探活一个源：优先用请求里的地址，没有就给已保存配置。"""
    if payload.base_url:
        try:
            source = validate_source(payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        if not payload.id:
            raise HTTPException(status_code=422, detail="需要提供 id 或 base_url")
        saved = {s.id: s for s in await store.load_sources(db)}
        source = saved.get(payload.id)
        if source is None:
            raise HTTPException(status_code=404, detail=f"源不存在：{payload.id}")

    ok, message, elapsed = await store.probe_source(source)
    # 探活结果同步写进健康度：通了立刻解除熔断，挂了按阶梯降权
    health = await store.load_health(db)
    state = health.get(source.id)
    if state is None:
        from app.services.media_sources import SourceHealth

        state = SourceHealth(source_id=source.id)
        health[source.id] = state
    if ok:
        state.record_ok(elapsed)
    else:
        state.record_fail(message)
    await store.save_health(db, health)

    return {
        "ok": ok,
        "message": message,
        "latency_ms": elapsed,
        "health": _health_dict(state),
    }


@router.get("/search")
async def search_sources(
    q: str = Query(..., min_length=1, max_length=80, description="搜索关键词"),
    page: int = Query(1, ge=1, le=5),
    db: AsyncSession = Depends(get_db),
):
    """聚合搜索：并发查所有启用源，按「标题 + 年份」合并同名结果。"""
    sources = await store.load_sources(db)
    if not sources:
        raise HTTPException(status_code=409, detail="还没有配置任何在线源")
    health = await store.load_health(db)
    report = await store.search_all(sources, health, q.strip(), page)
    await store.save_health(db, health)

    return {
        "keyword": report.keyword,
        "total": len(report.items),
        "skipped_sources": report.skipped,
        "items": [
            {
                "key": item.key,
                "title": item.title,
                "year": item.year,
                "poster": item.poster,
                "source_count": item.source_count,
                "offers": [
                    {
                        "source_id": offer.source_id,
                        "vod_id": offer.vod_id,
                        "remarks": offer.remarks,
                    }
                    for offer in item.offers
                ],
            }
            for item in report.items
        ],
        "sources": [
            {
                "source_id": state.source_id,
                "latency_ms": state.latency_ms,
                "fail_streak": state.fail_streak,
                "available": state.is_available(),
                "last_error": state.last_error,
            }
            for state in report.health
        ],
    }


@router.post("/resolve")
async def resolve_source(payload: ResolvePayload, db: AsyncSession = Depends(get_db)):
    """解析单条：返回线路与集数，供在线播放使用。"""
    sources = {s.id: s for s in await store.load_sources(db)}
    source = sources.get(payload.source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"源不存在：{payload.source_id}")

    health = await store.load_health(db)
    item, groups = await store.resolve_item(source, payload.vod_id, health)
    await store.save_health(db, health)

    if item is None:
        raise HTTPException(status_code=502, detail="该源没有返回可用的播放地址")

    return {
        "source_id": source.id,
        "vod_id": item.vod_id,
        "title": item.title,
        "year": item.year,
        "poster": item.poster,
        "groups": [
            {
                "flag": group.flag,
                "episodes": [
                    {"name": ep.name, "url": ep.url, "direct": ep.direct}
                    for ep in group.episodes
                ],
            }
            for group in groups
        ],
    }
