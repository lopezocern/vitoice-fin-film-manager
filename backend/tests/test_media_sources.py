"""自定义在线源：解析、聚合、健康度、配置校验。

这里全是纯逻辑与编排，不发真实网络请求（`search_source` 被 monkeypatch）。
真实采集站的返回体极脏，所以解析用例刻意用了畸形样本。
"""

from __future__ import annotations

import pytest

from app.services import media_sources_store as store
from app.services.media_sources import (
    MediaSource,
    SourceHealth,
    SourceItem,
    aggregate_items,
    cooldown_for_failures,
    extract_year,
    is_direct_stream,
    normalize_title,
    parse_cms_list,
    parse_play_groups,
    slugify_source_id,
    validate_source,
    validate_sources,
)


# ---------------------------------------------------------------------------
# 标题归一化 / 年份
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("进击的巨人 1080P", "进击的巨人"),
        ("【中字】进击的巨人", "进击的巨人"),
        ("进击的巨人 Final Season (2023)", "进击的巨人finalseason"),
        ("Spider-Man: No Way Home", "spidermannowayhome"),
        ("   ", ""),
    ],
)
def test_normalize_title_strips_noise(raw: str, expected: str) -> None:
    assert normalize_title(raw) == expected


def test_extract_year_prefers_explicit_field() -> None:
    assert extract_year("2024", "某电影 1999") == 2024
    assert extract_year(None, "沙丘 2021 加长版") == 2021
    assert extract_year("", None) is None


def test_slugify_source_id_keeps_cjk_and_falls_back_for_symbols() -> None:
    assert slugify_source_id("高清采集 站 A") == "高清采集-站-a"
    assert slugify_source_id("！！！").startswith("src-")


# ---------------------------------------------------------------------------
# 苹果 CMS 返回体解析
# ---------------------------------------------------------------------------


def test_parse_cms_list_accepts_dict_and_string_ids() -> None:
    payload = {
        "list": {
            "vod_id": 12345,
            "vod_name": "沙丘 2021 1080P",
            "vod_pic": "https://img/x.jpg",
            "vod_remarks": "HD",
        }
    }
    items = parse_cms_list(payload, "src-a")
    assert len(items) == 1
    item = items[0]
    assert item.vod_id == "12345"
    assert item.year == 2021
    assert item.poster == "https://img/x.jpg"
    assert item.remarks == "HD"


def test_parse_cms_list_skips_entries_without_id_or_title() -> None:
    payload = {"list": [{"vod_id": 1}, {"vod_name": "无 id"}, {"vod_id": 2, "vod_name": "OK"}]}
    items = parse_cms_list(payload, "src-a")
    assert [i.title for i in items] == ["OK"]


def test_parse_play_groups_handles_multiple_lines_and_messy_names() -> None:
    groups = parse_play_groups(
        "lzm3u8$$$bfzym3u8",
        "第01集$https://a.example/1.m3u8#第02集$https://a.example/2.m3u8"
        "$$$https://b.example/index.m3u8",
    )
    assert [g.flag for g in groups] == ["lzm3u8", "bfzym3u8"]
    assert [e.name for e in groups[0].episodes] == ["第01集", "第02集"]
    # 没有「集名$」前缀时自动生成集名，并保留地址
    assert groups[1].episodes[0].name == "第1集"
    assert groups[1].episodes[0].url == "https://b.example/index.m3u8"
    assert groups[1].episodes[0].direct is True


def test_parse_play_groups_drops_empty_entries() -> None:
    groups = parse_play_groups("m3u8", "第01集$#第02集$https://a/2.m3u8#")
    assert len(groups) == 1
    assert len(groups[0].episodes) == 1


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://a/x.m3u8", True),
        ("https://a/x.mp4?token=1", True),
        ("https://a/live/index.m3u8", True),
        ("https://a/play/page.html", False),
        ("", False),
    ],
)
def test_is_direct_stream(url: str, expected: bool) -> None:
    assert is_direct_stream(url) is expected


# ---------------------------------------------------------------------------
# 跨源聚合
# ---------------------------------------------------------------------------


def test_aggregate_merges_same_title_and_year_across_sources() -> None:
    per_source = {
        "src-a": [SourceItem("src-a", "1", "沙丘 2021 1080P", 2021, None, "HD")],
        "src-b": [
            SourceItem("src-b", "9", "沙丘", 2021, "https://img/b.jpg", "超清"),
            SourceItem("src-b", "10", "别的片子", 2020, None, None),
        ],
    }
    merged = aggregate_items(per_source)
    top = merged[0]
    assert top.year == 2021
    assert top.source_count == 2
    # 封面从有图的那条补齐
    assert top.poster == "https://img/b.jpg"
    assert len(merged) == 2


def test_aggregate_treats_missing_year_as_wildcard() -> None:
    per_source = {
        "src-a": [SourceItem("src-a", "1", "无年份片", None, None, None)],
        "src-b": [SourceItem("src-b", "2", "无年份片", 2019, None, None)],
    }
    merged = aggregate_items(per_source)
    # 一个站不返年份不应导致两条重复结果
    assert len(merged) == 1
    assert merged[0].year == 2019


# ---------------------------------------------------------------------------
# 健康度阶梯熔断
# ---------------------------------------------------------------------------


def test_cooldown_tiers() -> None:
    assert cooldown_for_failures(0) == 0
    assert cooldown_for_failures(2) == 0
    assert cooldown_for_failures(3) == 30 * 60
    assert cooldown_for_failures(4) == 24 * 3600
    assert cooldown_for_failures(9) == 7 * 24 * 3600


def test_health_recovers_on_success() -> None:
    state = SourceHealth(source_id="src-a")
    for _ in range(3):
        state.record_fail("boom")
    assert state.is_available() is False
    assert state.fail_streak == 3

    state.record_ok(120)
    assert state.is_available() is True
    assert state.fail_streak == 0
    assert state.latency_ms == 120
    assert state.last_error is None


# ---------------------------------------------------------------------------
# 配置校验
# ---------------------------------------------------------------------------


def test_validate_source_normalizes_and_applies_defaults() -> None:
    source = validate_source({"name": "高清站点", "base_url": "https://v.example.com/"})
    assert source.id == "高清站点"
    assert source.base_url == "https://v.example.com"
    assert source.api_path == "api.php/provide/vod"
    assert source.api_url() == "https://v.example.com/api.php/provide/vod/"


@pytest.mark.parametrize(
    ("payload", "fragment"),
    [
        ({"base_url": "https://a.com"}, "名称不能为空"),
        ({"name": "x", "base_url": "ftp://a.com"}, "http"),
        ({"name": "x", "base_url": "https://a.com", "api_path": "https://b/api"}, "相对路径"),
        ({"name": "x", "base_url": "https://a.com", "kind": "nope"}, "不支持的源类型"),
        ({"name": "x", "base_url": "https://a.com", "timeout": "abc"}, "timeout"),
        ({"name": "x", "base_url": "https://a.com", "headers": ["a"]}, "headers"),
    ],
)
def test_validate_source_rejects_bad_config(payload: dict, fragment: str) -> None:
    with pytest.raises(ValueError) as exc:
        validate_source(payload)
    assert fragment in str(exc.value)


def test_validate_sources_rejects_duplicate_ids() -> None:
    with pytest.raises(ValueError) as exc:
        validate_sources(
            [
                {"name": "A", "base_url": "https://a.com", "id": "same"},
                {"name": "B", "base_url": "https://b.com", "id": "same"},
            ]
        )
    assert "重复" in str(exc.value)


# ---------------------------------------------------------------------------
# 编排：单源失败不影响整体
# ---------------------------------------------------------------------------


async def test_search_all_degrades_single_source_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    sources = [
        MediaSource(id="ok", name="OK", base_url="https://ok.example"),
        MediaSource(id="bad", name="BAD", base_url="https://bad.example"),
    ]
    health: dict[str, SourceHealth] = {}

    async def fake_search(source: MediaSource, keyword: str, page: int = 1):
        if source.id == "bad":
            raise RuntimeError("timeout")
        return [SourceItem("ok", "1", "沙丘", 2021, None, "HD")], 80

    monkeypatch.setattr(store, "search_source", fake_search)

    report = await store.search_all(sources, health, "沙丘")

    assert [i.title for i in report.items] == ["沙丘"]
    assert health["bad"].fail_streak == 1
    assert health["bad"].last_error == "timeout"
    assert health["ok"].fail_streak == 0
    assert report.skipped == []


async def test_search_all_skips_tripped_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    sources = [
        MediaSource(id="ok", name="OK", base_url="https://ok.example"),
        MediaSource(id="dead", name="DEAD", base_url="https://dead.example"),
    ]
    tripped = SourceHealth(source_id="dead")
    for _ in range(3):
        tripped.record_fail("boom")
    health = {"dead": tripped}

    calls: list[str] = []

    async def fake_search(source: MediaSource, keyword: str, page: int = 1):
        calls.append(source.id)
        return [], 10

    monkeypatch.setattr(store, "search_source", fake_search)

    report = await store.search_all(sources, health, "任何")
    assert calls == ["ok"]
    assert report.skipped == ["dead"]


async def test_probe_source_reports_success_even_without_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search(source: MediaSource, keyword: str, page: int = 1):
        return [], 42

    monkeypatch.setattr(store, "search_source", fake_search)
    ok, message, _ = await store.probe_source(
        MediaSource(id="a", name="A", base_url="https://a.example")
    )
    # 关键词没数据不等于源坏了：能拿到合法响应就算可用
    assert ok is True
    assert "可用" in message
