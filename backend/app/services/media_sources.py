"""可插拔在线媒体源适配层（自定义源 / 聚合搜索 / 源健康度）。

设计目标（对标 LibreTV 的采集站聚合 + 我们的本地库）：

1. **同一份源配置同时服务搜索与播放**：一个源 = 一个 HTTP JSON 接口（苹果 CMS v10
   `/api.php/provide/vod/`），搜索拿列表，详情拿剧集与播放地址。
2. **聚合结果按「标题 + 年份」归一化合并**：同一部片在多个源里只出现一次，
   展开后可以看到各源的质量/线路，避免"同一个名字刷满整屏"。
3. **源健康度阶梯停用**：连续失败的源自动降权（30 分钟 → 24 小时 → 7 天），
   成功一次立刻恢复；用户不用手动盯着哪些源挂了。

关于复用边界：LibreTV（Next.js）、Peach（AGPL-3.0）、Amane（GPLv3）的**代码不可抄**
（本项目 MIT），但「采集站协议是公开事实标准」「按源健康度熔断」这类机制可以自行实现。

本模块只做纯逻辑 + HTTP 抓取，不依赖 FastAPI 的请求上下文，便于单测。
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.proxy import get_proxy_url
from app.services.ssrf import validate_http_url

# ---------------------------------------------------------------------------
# 源配置
# ---------------------------------------------------------------------------

#: 目前只实现苹果 CMS v10 点播接口；后续可扩 iptv_m3u / html 解析器。
SOURCE_KINDS = ("cms_vod",)

#: 默认接口路径（多数采集站部署在同一路径下）。
DEFAULT_API_PATH = "api.php/provide/vod"

DEFAULT_TIMEOUT = 12.0


@dataclass(slots=True)
class MediaSource:
    """一个可搜索/可播放的在线源。

    ``id`` 由用户可读名称派生并保持稳定（改名不改 id），健康度与缓存都按它索引。
    """

    id: str
    name: str
    base_url: str
    kind: str = "cms_vod"
    api_path: str = DEFAULT_API_PATH
    enabled: bool = True
    timeout: float = DEFAULT_TIMEOUT
    headers: dict[str, str] = field(default_factory=dict)

    def api_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/{self.api_path.lstrip('/')}/"


def slugify_source_id(name: str) -> str:
    """把源名称转成稳定 id（中文保留，空白与符号折叠为 `-`）。"""
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "-", (name or "").strip().lower())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    if cleaned:
        return cleaned[:48]
    # 名称全是符号时退化为内容哈希，避免空 id
    return "src-" + hashlib.sha1((name or "").encode("utf-8")).hexdigest()[:8]


def validate_source(raw: Any) -> MediaSource:
    """校验并规范化一条源配置；不合法时抛 ``ValueError``（中文原因）。"""
    if not isinstance(raw, dict):
        raise ValueError("源配置必须是对象")

    name = str(raw.get("name") or "").strip()
    if not name:
        raise ValueError("源名称不能为空")

    kind = str(raw.get("kind") or "cms_vod").strip()
    if kind not in SOURCE_KINDS:
        raise ValueError(f"不支持的源类型：{kind}")

    base_url = str(raw.get("base_url") or "").strip().rstrip("/")
    if not base_url:
        raise ValueError(f"源「{name}」缺少 base_url")
    try:
        validate_http_url(base_url)
    except ValueError as exc:
        raise ValueError(f"源「{name}」地址不可用：{exc}") from exc

    api_path = str(raw.get("api_path") or DEFAULT_API_PATH).strip().strip("/")
    # 只允许相对路径：绝对地址会让 base_url 变成摆设，也绕开上面的校验语义
    if "://" in api_path:
        raise ValueError(f"源「{name}」的 api_path 必须是相对路径")

    try:
        timeout = float(raw.get("timeout") or DEFAULT_TIMEOUT)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"源「{name}」的 timeout 不是数字") from exc
    timeout = min(max(timeout, 3.0), 60.0)

    headers_raw = raw.get("headers") or {}
    if not isinstance(headers_raw, dict):
        raise ValueError(f"源「{name}」的 headers 必须是对象")
    headers = {str(k): str(v) for k, v in headers_raw.items()}

    source_id = str(raw.get("id") or "").strip() or slugify_source_id(name)

    return MediaSource(
        id=source_id,
        name=name,
        base_url=base_url,
        kind=kind,
        api_path=api_path,
        enabled=bool(raw.get("enabled", True)),
        timeout=timeout,
        headers=headers,
    )


def validate_sources(raw_list: Any) -> list[MediaSource]:
    """校验整份源列表：逐条校验 + id 去重（重复 id 会让健康度串台）。"""
    if not isinstance(raw_list, list):
        raise ValueError("sources 必须是数组")
    sources: list[MediaSource] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_list):
        try:
            source = validate_source(raw)
        except ValueError as exc:
            raise ValueError(f"第 {index + 1} 条：{exc}") from exc
        if source.id in seen:
            raise ValueError(f"源 id 重复：{source.id}（改名时请保留原 id）")
        seen.add(source.id)
        sources.append(source)
    return sources


# ---------------------------------------------------------------------------
# 苹果 CMS v10 解析
# ---------------------------------------------------------------------------

#: 标题里常见的噪声尾巴：清晰度/字幕/语言标记，归一化时要剥掉，
#: 否则「进击的巨人 第一季 1080P」和「进击的巨人 第一季」会被当成两部片。
_NOISE_PATTERN = re.compile(
    r"(?i)(?:"
    r"\b(?:hd|sd|uhd|4k|8k|1080p|720p|2160p|480p|bluray|web-?dl|hdtv|remux)\b"
    r"|中字|中文字幕|简中|繁中|无字|字幕"
    r"|国语|粤语|日语|英语|双语|原声"
    r"|全集|完结|更新至?\d+集?|第\d+季"
    r"|[\[【(（][^\]】)）]{0,12}[\]】)）]"
    r")"
)

_YEAR_PATTERN = re.compile(r"(19\d{2}|20\d{2})")

_ALNUM_CJK = re.compile(r"[^\w\u4e00-\u9fff]+")

#: 标题里内嵌的年份。归一化时剥掉它：年份已经是分组键的独立维度，
#: 留在标题里会让「沙丘 2021」和「沙丘」被当成两部片，跨源合并直接失效。
_EMBEDDED_YEAR = re.compile(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)")


def normalize_title(title: str) -> str:
    """归一化标题：去噪、去年份、去标点、转小写，用于跨源同名合并。"""
    text = (title or "").strip()
    if not text:
        return ""
    text = _NOISE_PATTERN.sub(" ", text)
    text = _EMBEDDED_YEAR.sub(" ", text)
    text = _ALNUM_CJK.sub("", text.lower())
    return text


def extract_year(*candidates: Any) -> int | None:
    """从年份字段或标题里取四位数年份。"""
    for candidate in candidates:
        if candidate is None:
            continue
        match = _YEAR_PATTERN.search(str(candidate))
        if match:
            return int(match.group(1))
    return None


@dataclass(slots=True)
class PlayEpisode:
    name: str
    url: str
    #: 直链（m3u8/mp4/flv）为 True；需要浏览器打开或二次解析为 False
    direct: bool


@dataclass(slots=True)
class PlayGroup:
    """一条线路（苹果 CMS 的 `vod_play_from` 一项）。"""

    flag: str
    episodes: list[PlayEpisode]


_DIRECT_SUFFIXES = (".m3u8", ".mp4", ".flv", ".ts", ".mkv", ".webm")


def is_direct_stream(url: str) -> bool:
    """判断播放地址是否可直接交给播放器（而非需要解析的网页）。"""
    if not url:
        return False
    lowered = url.lower().split("?")[0]
    if lowered.endswith(_DIRECT_SUFFIXES):
        return True
    # 无扩展名但明显是 HLS 端点（如 /hls/index.m3u8 已覆盖；这里兜底 aliyun 风格）
    return "/hls/" in lowered or lowered.endswith("/index")


def parse_play_groups(play_from: str | None, play_url: str | None) -> list[PlayGroup]:
    """解析 `$$$` 分组的线路与 `#` 分隔的集数。

    真实采集站数据很脏：可能缺字段、集名缺失、地址里带 `$`。这里逐条容错，
    解析不出地址的条目直接丢弃，而不是让整条线路失败。
    """
    if not play_url:
        return []
    flags = [f.strip() for f in (play_from or "").split("$$$")] if play_from else []
    groups: list[PlayGroup] = []

    for index, raw_group in enumerate(play_url.split("$$$")):
        flag = flags[index].strip() if index < len(flags) and flags[index].strip() else f"线路{index + 1}"
        episodes: list[PlayEpisode] = []
        for raw_ep in raw_group.split("#"):
            item = raw_ep.strip()
            if not item:
                continue
            # 集名$地址：用第一个 `$` 切分，地址里再出现 `$` 不影响
            if "$" in item:
                name, _, url = item.partition("$")
            else:
                name, url = "", item
            url = url.strip()
            if not url:
                continue
            episodes.append(
                PlayEpisode(
                    name=name.strip() or f"第{len(episodes) + 1}集",
                    url=url,
                    direct=is_direct_stream(url),
                )
            )
        if episodes:
            groups.append(PlayGroup(flag=flag, episodes=episodes))
    return groups


@dataclass(slots=True)
class SourceItem:
    """搜索结果里的一个条目（来自某个源）。"""

    source_id: str
    vod_id: str
    title: str
    year: int | None
    poster: str | None
    remarks: str | None
    play_from: str | None = None
    play_url: str | None = None


def parse_cms_list(payload: Any, source_id: str) -> list[SourceItem]:
    """解析 `ac=detail` 的返回体。

    兼容两种常见畸形：`list` 是对象而不是数组、`vod_id` 是数字/字符串混用。
    """
    if not isinstance(payload, dict):
        return []
    raw_items = payload.get("list")
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list):
        return []

    items: list[SourceItem] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("vod_name") or raw.get("vod_title") or "").strip()
        vod_id = str(raw.get("vod_id") or "").strip()
        if not title or not vod_id:
            continue
        items.append(
            SourceItem(
                source_id=source_id,
                vod_id=vod_id,
                title=title,
                year=extract_year(raw.get("vod_year"), title),
                poster=str(raw.get("vod_pic") or "").strip() or None,
                remarks=str(raw.get("vod_remarks") or "").strip() or None,
                play_from=str(raw.get("vod_play_from") or "") or None,
                play_url=str(raw.get("vod_play_url") or "") or None,
            )
        )
    return items


@dataclass(slots=True)
class AggregatedItem:
    """跨源合并后的条目：同名同年的多个来源挂在 `offers` 下。"""

    key: str
    title: str
    year: int | None
    poster: str | None
    offers: list[SourceItem]

    @property
    def source_count(self) -> int:
        return len({offer.source_id for offer in self.offers})


def aggregate_items(per_source: dict[str, list[SourceItem]]) -> list[AggregatedItem]:
    """按「归一化标题 + 年份」合并多源结果。

    年份缺失的条目按通配处理：同一标题下只有一个已知年份分组时并入它，
    有多个候选时单独成组——宁可多出一组，也不要把 1984 和 2021 的两部《沙丘》
    错并成一条。
    """
    # 1) 先按归一化标题聚拢，保留原始条目以便后面按年份细分
    by_norm: dict[str, list[SourceItem]] = {}
    for items in per_source.values():
        for item in items:
            norm = normalize_title(item.title) or item.title.strip().lower()
            by_norm.setdefault(norm, []).append(item)

    merged: dict[str, AggregatedItem] = {}

    def add(bucket_key: str, item: SourceItem) -> None:
        existing = merged.get(bucket_key)
        if existing is None:
            merged[bucket_key] = AggregatedItem(
                key=bucket_key,
                title=item.title,
                year=item.year,
                poster=item.poster,
                offers=[item],
            )
            return
        existing.offers.append(item)
        if existing.poster is None and item.poster:
            existing.poster = item.poster
        if existing.year is None and item.year:
            existing.year = item.year

    for norm, items in by_norm.items():
        known: dict[int, list[SourceItem]] = {}
        unknown: list[SourceItem] = []
        for item in items:
            if item.year:
                known.setdefault(item.year, []).append(item)
            else:
                unknown.append(item)

        for year, bucket in known.items():
            for item in bucket:
                add(f"{norm}|{year}", item)

        if unknown:
            if len(known) == 1:
                # 唯一候选年：无年份条目几乎一定是它
                year = next(iter(known))
                for item in unknown:
                    add(f"{norm}|{year}", item)
            else:
                for item in unknown:
                    add(f"{norm}|*", item)

    # 源多的排前面：更可能有多条可用线路
    return sorted(
        merged.values(),
        key=lambda agg: (-agg.source_count, agg.title),
    )


# ---------------------------------------------------------------------------
# 源健康度（阶梯熔断）
# ---------------------------------------------------------------------------

#: 连续失败次数 → 熔断时长（秒）。
#: 1~2 次只是抖动；3 次开始短熔断避免反复拖慢聚合搜索；再失败就长时间弃用。
FAIL_TIERS: tuple[tuple[int, int], ...] = (
    (5, 7 * 24 * 3600),  # >= 5 次：7 天
    (4, 24 * 3600),  # 4 次：24 小时
    (3, 30 * 60),  # 3 次：30 分钟
)


def cooldown_for_failures(fail_streak: int) -> int:
    """连续失败 ``fail_streak`` 次后应熔断的秒数；未达阈值返回 0。"""
    for threshold, seconds in FAIL_TIERS:
        if fail_streak >= threshold:
            return seconds
    return 0


@dataclass(slots=True)
class SourceHealth:
    source_id: str
    fail_streak: int = 0
    disabled_until: float = 0.0
    last_ok_at: float = 0.0
    last_error: str | None = None
    latency_ms: int | None = None

    def is_available(self, now: float | None = None) -> bool:
        return (now or time.time()) >= self.disabled_until

    def record_ok(self, latency_ms: int, now: float | None = None) -> None:
        self.fail_streak = 0
        self.disabled_until = 0.0
        self.last_ok_at = now or time.time()
        self.last_error = None
        self.latency_ms = latency_ms

    def record_fail(self, error: str, now: float | None = None) -> None:
        current = now or time.time()
        self.fail_streak += 1
        cooldown = cooldown_for_failures(self.fail_streak)
        if cooldown:
            self.disabled_until = current + cooldown
        self.last_error = error[:200]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "fail_streak": self.fail_streak,
            "disabled_until": self.disabled_until,
            "last_ok_at": self.last_ok_at,
            "last_error": self.last_error,
            "latency_ms": self.latency_ms,
        }

    @classmethod
    def from_dict(cls, data: Any) -> SourceHealth | None:
        if not isinstance(data, dict) or not data.get("source_id"):
            return None
        return cls(
            source_id=str(data["source_id"]),
            fail_streak=int(data.get("fail_streak") or 0),
            disabled_until=float(data.get("disabled_until") or 0.0),
            last_ok_at=float(data.get("last_ok_at") or 0.0),
            last_error=(str(data["last_error"]) if data.get("last_error") else None),
            latency_ms=(int(data["latency_ms"]) if data.get("latency_ms") is not None else None),
        )


# ---------------------------------------------------------------------------
# HTTP 抓取
# ---------------------------------------------------------------------------


class SourceFetchError(RuntimeError):
    """源请求失败（网络错误 / 非 2xx / 非 JSON）。"""


def is_local_host(value: str | None) -> bool:
    """判断目标是否在本机/局域网内（接受完整 URL 或裸主机名）。

    这类地址**不能走系统代理**：开了代理的用户访问 127.0.0.1 或 NAS 上的
    采集站会直接 ConnectError（请求被送到代理服务器上去了）。
    """
    raw = (value or "").strip()
    if not raw:
        return False
    host = (urlparse(raw).hostname or "") if "://" in raw else raw
    lowered = host.strip().lower().strip("[]")
    if not lowered:
        return False
    if lowered in ("localhost", "::1"):
        return True
    try:
        import ipaddress

        ip = ipaddress.ip_address(lowered)
        return ip.is_loopback or ip.is_private or ip.is_link_local
    except ValueError:
        pass
    # 域名形式：解析一次判断（解析失败就当外网，交给代理）
    try:
        import socket
        import ipaddress

        ip = ipaddress.ip_address(socket.gethostbyname(lowered))
        return ip.is_loopback or ip.is_private or ip.is_link_local
    except Exception:
        return False


async def fetch_cms(
    source: MediaSource,
    *,
    keyword: str = "",
    vod_id: str = "",
    page: int = 1,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """调用苹果 CMS 的 `ac=detail` 接口并返回 JSON。

    - 搜索：`wd=keyword`
    - 详情：`ids=vod_id`
    - 统一走 SSRF 校验 + 可选代理，超时由源配置控制
    """
    validate_http_url(source.base_url)

    params: dict[str, Any] = {"ac": "detail"}
    if vod_id:
        params["ids"] = vod_id
    else:
        params["wd"] = keyword
    params["pg"] = max(1, page)

    headers = {"User-Agent": "vitoice/3.0 media-source", "Accept": "application/json"}
    headers.update(source.headers)

    owns_client = client is None
    if owns_client:
        # 本机/局域网源直连，不套系统代理（否则本地假源、NAS 采集站全连不上）
        proxy = None if is_local_host(source.base_url) else await get_proxy_url()
        client = httpx.AsyncClient(
            timeout=source.timeout,
            proxy=proxy,
            follow_redirects=True,
        )
    assert client is not None
    try:
        started = time.perf_counter()
        response = await client.get(source.api_url(), params=params, headers=headers)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            raise SourceFetchError(f"HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise SourceFetchError("返回内容不是 JSON（可能被站点拦截或路径不对）") from exc
        if not isinstance(payload, dict):
            raise SourceFetchError("返回结构异常")
        # 部分站点把耗时带回来，供健康度使用
        payload.setdefault("_vitoice_latency_ms", elapsed_ms)
        return payload
    except httpx.HTTPError as exc:
        raise SourceFetchError(f"请求失败：{exc.__class__.__name__}") from exc
    finally:
        if owns_client:
            await client.aclose()


async def search_source(
    source: MediaSource, keyword: str, page: int = 1
) -> tuple[list[SourceItem], int]:
    """搜索单个源，返回 (条目, 耗时毫秒)。"""
    payload = await fetch_cms(source, keyword=keyword, page=page)
    items = parse_cms_list(payload, source.id)
    return items, int(payload.get("_vitoice_latency_ms") or 0)


async def resolve_source_item(
    source: MediaSource, vod_id: str
) -> tuple[SourceItem | None, list[PlayGroup], int]:
    """拉取单条详情并解析播放线路，返回 (条目, 线路, 耗时毫秒)。"""
    payload = await fetch_cms(source, vod_id=vod_id)
    items = parse_cms_list(payload, source.id)
    if not items:
        return None, [], int(payload.get("_vitoice_latency_ms") or 0)
    item = items[0]
    groups = parse_play_groups(item.play_from, item.play_url)
    return item, groups, int(payload.get("_vitoice_latency_ms") or 0)
