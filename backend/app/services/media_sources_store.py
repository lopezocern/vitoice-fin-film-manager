"""自定义在线源的事务层（配置读写 + 健康度持久化 + 聚合搜索编排）。

拆出来的原因：`services/media_sources.py` 只做纯解析与单源抓取，便于单测；
这里才碰数据库与并发，两层的失败语义不同（配置错误 422 / 源失败只降权）。
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SettingType
from app.models.setting import Setting
from app.services.media_sources import (
    AggregatedItem,
    MediaSource,
    SourceHealth,
    SourceItem,
    aggregate_items,
    resolve_source_item,
    search_source,
    validate_sources,
)

SOURCES_KEY = "media_sources"
HEALTH_KEY = "media_source_health"

#: 聚合搜索同时请求的最大源数（再多就不是"搜索"而是"扫全站"了）
MAX_PARALLEL_SOURCES = 8


@dataclass(slots=True)
class SourceSearchReport:
    """一次聚合搜索的完整结果，含每个源的表现，前端可直接渲染"哪些源失败"。"""

    keyword: str
    items: list[AggregatedItem]
    health: list[SourceHealth]
    #: 因为熔断被跳过的源 id
    skipped: list[str]


async def _read_json_setting(db: AsyncSession, key: str, default: Any) -> Any:
    result = await db.execute(select(Setting.value).where(Setting.key == key))
    raw = result.scalar()
    if not raw:
        return default
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default
    return parsed if isinstance(parsed, type(default)) else default


async def _write_json_setting(
    db: AsyncSession, key: str, value: Any, category: str = "network"
) -> None:
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting is None:
        setting = Setting(
            key=key,
            value="",
            type=SettingType.JSON,
            category=category,
        )
        db.add(setting)
    setting.value = json.dumps(value, ensure_ascii=False)
    await db.flush()


async def load_sources(db: AsyncSession) -> list[MediaSource]:
    """读取已保存的源列表；脏数据整体忽略而不是让接口 500。"""
    raw = await _read_json_setting(db, SOURCES_KEY, {"sources": []})
    try:
        return validate_sources(raw.get("sources") or [])
    except ValueError:
        # 配置被手改坏时，宁可当作"没有源"，也不要让整个在线播放页崩掉
        return []


async def save_sources(db: AsyncSession, sources: list[MediaSource]) -> list[MediaSource]:
    payload = {
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
            }
            for s in sources
        ]
    }
    await _write_json_setting(db, SOURCES_KEY, payload)
    return sources


async def load_health(db: AsyncSession) -> dict[str, SourceHealth]:
    raw = await _read_json_setting(db, HEALTH_KEY, {"entries": []})
    health: dict[str, SourceHealth] = {}
    for entry in raw.get("entries") or []:
        parsed = SourceHealth.from_dict(entry)
        if parsed:
            health[parsed.source_id] = parsed
    return health


async def save_health(db: AsyncSession, health: dict[str, SourceHealth]) -> None:
    payload = {"entries": [h.to_dict() for h in health.values()]}
    await _write_json_setting(db, HEALTH_KEY, payload)


def enabled_sources(sources: list[MediaSource]) -> list[MediaSource]:
    return [s for s in sources if s.enabled]


async def search_all(
    sources: list[MediaSource],
    health: dict[str, SourceHealth],
    keyword: str,
    page: int = 1,
) -> SourceSearchReport:
    """并发搜索所有启用且未熔断的源，合并同名结果。

    单源失败不影响整体：记录到健康度并降权，聚合结果照常返回。
    这样"某个源挂了"不会让用户看到整页报错。
    """
    now = time.time()
    active = [s for s in enabled_sources(sources) if health.get(s.id) is None or health[s.id].is_available(now)]
    skipped = [s.id for s in enabled_sources(sources) if s not in active]
    active = active[:MAX_PARALLEL_SOURCES]

    per_source: dict[str, list[SourceItem]] = {}

    async def run_one(source: MediaSource) -> None:
        state = health.get(source.id) or SourceHealth(source_id=source.id)
        health[source.id] = state
        try:
            items, latency_ms = await search_source(source, keyword, page)
        except Exception as exc:  # 源是外部系统，任何异常都只降权不抛出
            state.record_fail(str(exc))
            return
        state.record_ok(latency_ms)
        per_source[source.id] = items

    await asyncio.gather(*(run_one(source) for source in active))

    merged = aggregate_items(per_source)
    ordered_health = [health[s.id] for s in active if s.id in health]
    return SourceSearchReport(
        keyword=keyword,
        items=merged,
        health=ordered_health,
        skipped=skipped,
    )


async def resolve_item(
    source: MediaSource, vod_id: str, health: dict[str, SourceHealth]
) -> tuple[SourceItem | None, list[Any]]:
    """解析单条详情；失败同样只降权。"""
    state = health.get(source.id) or SourceHealth(source_id=source.id)
    health[source.id] = state
    try:
        item, groups, latency_ms = await resolve_source_item(source, vod_id)
    except Exception as exc:
        state.record_fail(str(exc))
        return None, []
    state.record_ok(latency_ms)
    return item, groups


async def probe_source(source: MediaSource) -> tuple[bool, str, int]:
    """探活：用一个极常见的词搜一次，返回 (是否可用, 说明, 耗时毫秒)。"""
    started = time.perf_counter()
    try:
        items, _ = await search_source(source, "测试")
    except Exception as exc:
        return False, str(exc), int((time.perf_counter() - started) * 1000)
    elapsed = int((time.perf_counter() - started) * 1000)
    # 搜不到结果不代表源坏了（关键词可能确实没数据），能拿到合法 JSON 就算通
    return True, f"接口可用，示例结果 {len(items)} 条", elapsed
