"""import-network：一次入库要保留整条线路的「源 + 线路 + 集数」。

在线片库入库时如果只存当前播放的那一条 URL，详情页和播放器就无法换源——
用户重新打开这部剧只能看到一集。这组用例锁定三件事：
- 传 urls 时全部落库，并按 url 去重；
- 当前播放的那条排第一（播放器默认选中它）；
- 不传 urls 时保持旧行为（只落一条）。
"""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import LibraryType
from app.models.library import MediaLibrary


async def _library(db: AsyncSession, name: str, root: str) -> MediaLibrary:
    lib = MediaLibrary(name=name, type=LibraryType.VIDEO, root_path=root)
    db.add(lib)
    await db.flush()
    return lib


async def test_import_keeps_all_lines_and_puts_playing_first(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    lib = await _library(db_session, "在线入库", "C:/online-a")
    payload = {
        "library_id": lib.id,
        "url": "https://cdn.example.com/ep2.m3u8",
        "title": "沙丘",
        "source_name": "示例采集站",
        "source_id": "demo",
        "urls": [
            {"url": "https://cdn.example.com/ep1.m3u8", "line_name": "lzm3u8", "episode_name": "第01集", "episode_index": 0},
            {"url": "https://cdn.example.com/ep2.m3u8", "line_name": "lzm3u8", "episode_name": "第02集", "episode_index": 1},
            {"url": "https://cdn.example.com/bf.m3u8", "line_name": "bfzy", "episode_name": "正片", "episode_index": 0},
            # 重复 url 应去重，而不是落两条
            {"url": "https://cdn.example.com/ep2.m3u8", "line_name": "lzm3u8", "episode_name": "第02集", "episode_index": 1},
        ],
    }

    resp = await api_client.post("/api/media/import-network", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert data["media_type"] == "network"
    assert data["series_title"] == "沙丘"

    urls = sorted(data["urls"], key=lambda u: u["id"])
    assert len(urls) == 3

    primary = urls[0]
    assert primary["url"] == "https://cdn.example.com/ep2.m3u8"
    assert primary["line_name"] == "lzm3u8"
    assert primary["episode_name"] == "第02集"
    assert primary["episode_index"] == 1
    assert primary["source_name"] == "示例采集站"
    assert primary["source_id"] == "demo"

    assert {u["line_name"] for u in urls} == {"lzm3u8", "bfzy"}


async def test_import_without_urls_keeps_single_source(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    lib = await _library(db_session, "单条入库", "C:/online-b")
    resp = await api_client.post(
        "/api/media/import-network",
        json={"library_id": lib.id, "url": "https://cdn.example.com/solo.m3u8", "title": "单集"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()

    assert len(data["urls"]) == 1
    assert data["urls"][0]["url"] == "https://cdn.example.com/solo.m3u8"
    assert data["urls"][0]["line_name"] is None
    # 只有一条时不当作剧集
    assert data["series_title"] is None
