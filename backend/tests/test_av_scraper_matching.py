"""Regression tests for adult filename and 3xplanet URL matching."""

import httpx
import pytest

from app.services.av_scraper import (
    _fetch_3xplanet_page,
    _find_3xplanet_detail_url,
    _parse_3xplanet_html,
    parse_av_fancode,
)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("Tokyo-Hot-n0476.mp4", "N0476"),
        ("259LUXU-1100.mp4", "259LUXU-1100"),
        ("FC2-PPV-4903567.mp4", "FC2-PPV-4903567"),
        ("030315-819 Caribbean 大桥未久.mp4", "030315-819"),
        ("011015-780 Caribbean 大桥未久.mp4", "011015-780"),
        ("DASS-699-C.mp4", "DASS-699"),
    ],
)
def test_parse_av_fancode_special_families(filename: str, expected: str) -> None:
    assert parse_av_fancode(filename) == expected


@pytest.mark.parametrize(
    ("detail_html", "fancode", "expected"),
    [
        # 数字前缀番号：命中 uncen-leaked- 分类 slug
        (
            '<a href="/uncen-leaked-259luxu-1100/">259LUXU-1100</a>',
            "259LUXU-1100",
            "https://3xplanet.com/uncen-leaked-259luxu-1100/",
        ),
        # 字母前缀番号（MDG-166）同样命中——旧逻辑只认数字前缀导致这类番号漏掉
        (
            '<a href="/uncen-leaked-mdg-166/">(Mosaic Reduced) MDG-166</a>',
            "MDG-166",
            "https://3xplanet.com/uncen-leaked-mdg-166/",
        ),
    ],
)
def test_find_3xplanet_detail_url_prefixed_slug(
    detail_html: str, fancode: str, expected: str
) -> None:
    assert _find_3xplanet_detail_url(detail_html, fancode, "https://3xplanet.com") == expected


@pytest.mark.asyncio
async def test_fetch_3xplanet_bare_and_prefixed_slugs() -> None:
    """直接 slug 与 uncen-leaked- 前缀 slug 的抓取顺序。

    命中顺序：先试裸 slug，404 后回退到分类前缀变体。覆盖 Tokyo-Hot / 数字前缀 /
    FC2 / 字母前缀（MDG-166，仅存在于 uncen-leaked- 下）四类番号。
    """
    requested: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        pages = {
            "https://3xplanet.com/n0476/": "tokyo-hot-page",
            "https://3xplanet.com/uncen-leaked-259luxu-1100/": "luxu-page",
            "https://3xplanet.com/fc2-ppv-4903567/": "fc2-page",
            "https://3xplanet.com/uncen-leaked-mdg-166/": "leaked-page",
        }
        body = pages.get(str(request.url))
        return httpx.Response(200 if body else 404, text=body or "")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await _fetch_3xplanet_page(client, "N0476") == "tokyo-hot-page"
        assert await _fetch_3xplanet_page(client, "259LUXU-1100") == "luxu-page"
        assert await _fetch_3xplanet_page(client, "FC2-PPV-4903567") == "fc2-page"
        assert await _fetch_3xplanet_page(client, "MDG-166") == "leaked-page"

    assert "https://3xplanet.com/259luxu-1100/" in requested
    assert "https://3xplanet.com/uncen-leaked-259luxu-1100/" in requested
    # 字母前缀番号：裸 slug 先 404，随后命中 uncen-leaked- 变体
    assert "https://3xplanet.com/mdg-166/" in requested
    assert "https://3xplanet.com/uncen-leaked-mdg-166/" in requested


_LEGACY_3XPLANET_HTML = """
<html><head>
<meta property="og:image" content="https://3xplanetimg.com/images/2023/10/22/cover/s0/379998_cover.jpg">
</head><body>
<article>
  <h1>(Mosaic Reduced) 259LUXU-1100 ラグジュTV 1087 サンプルタイトル</h1>
  <p>Starring: Arisaka Miyuki</p>
  <p>Studio: Luxury TV</p>
  <p>Tags: UNCENSORED , Luxury TV , Arisaka Miyuki , Facial cumshots</p>
  <p>品番: 259LUXU-1100</p>
  <p>発売日: 2019/04/08</p>
  <p>収録時間: 69min</p>
  <p>メーカー: ラグジュTV</p>
  <p>ジャンル: 美脚 美尻 顔射 お姉さん</p>
  <p>出演者: 有坂深雪</p>
</article>
</body></html>
"""


def test_parse_3xplanet_legacy_layout_fills_fields() -> None:
    """旧版布局（无 dl.xplanet-specs）必须解析 article p 行。

    历史 bug：h1 阶段先写入 title 后，`if not result:` 守卫恒为 False，
    旧版解析块成为死代码，页面退化为 JSON-LD 兜底（genres/actresses 残缺、
    工作室名混入 actresses）。回归锁：旧版页面必须拿到完整字段，
    且日文行优先于英文行、ジャンル按空格拆分。
    """
    parsed = _parse_3xplanet_html(
        _LEGACY_3XPLANET_HTML, "259LUXU-1100", "https://3xplanet.com"
    )
    assert parsed is not None
    assert parsed["actresses"] == ["有坂深雪"]  # 日文行覆盖英文 Starring 行
    assert parsed["studio"] == "ラグジュTV"  # 日文行覆盖英文 Studio 行
    assert parsed["release_date"] == "2019-04-08"
    assert parsed["runtime_minutes"] == 69
    # ジャンル行以空格分隔 → 拆为独立标签，而非一个整串
    assert parsed["genres"] == ["美脚", "美尻", "顔射", "お姉さん"]
    assert "Luxury TV" not in parsed["actresses"]
    assert parsed["cover_url"].startswith("https://3xplanetimg")


def test_parse_3xplanet_new_layout_unchanged() -> None:
    """新版 dl.xplanet-specs 布局行为保持不变。"""
    html = """
    <html><body>
      <h1>VRPRD-206 サンプルタイトル</h1>
      <dl class="xplanet-specs">
        <dt>品番/Code</dt><dd>VRPRD-206</dd>
        <dt>発売日/Release Date</dt><dd>2026/08/29</dd>
        <dt>収録時間/Duration</dt><dd>64min</dd>
        <dt>メーカー/Studio</dt><dd>VRパラダイス</dd>
        <dt>ジャンル/Genres</dt><dd>美脚, 美尻, 顔射</dd>
        <dt>出演者/Actress</dt><dd>皆月ひかる</dd>
      </dl>
    </body></html>
    """
    parsed = _parse_3xplanet_html(html, "VRPRD-206", "https://3xplanet.com")
    assert parsed is not None
    assert parsed["title"] == "サンプルタイトル"
    assert parsed["release_date"] == "2026-08-29"
    assert parsed["runtime_minutes"] == 64
    assert parsed["studio"] == "VRパラダイス"
    assert parsed["genres"] == ["美脚", "美尻", "顔射"]
    assert parsed["actresses"] == ["皆月ひかる"]
