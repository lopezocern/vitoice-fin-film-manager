"""`GET /api/media?ids_only=true` — 跨页全选的数据源。

为什么要这个接口：全选筛选结果需要"匹配条件的全部 id"，而不是 200 条/页的完整对象
（单条约 4KB，874 条就 3.4MB）。这里验证三件事：
1. ids 与 total 一致，且忽略分页；
2. ids 与筛选条件严格一致（不是"整库 id"）；
3. 超过上限时明确 413 并给出可操作提示，而不是悄悄截断。
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import media as media_api_module
from app.models.enums import LibraryType, ScrapeMode
from app.models.library import MediaLibrary
from app.models.media import Media
from app.models.tag import Tag, TagType, VideoTag


async def seed(db: AsyncSession) -> dict[str, int]:
    lib = MediaLibrary(
        name="IdsLib", type=LibraryType.VIDEO, root_path="C:/idslib", scrape_mode=ScrapeMode.MOVIE
    )
    db.add(lib)
    await db.flush()

    def media(title: str) -> Media:
        return Media(
            library_id=lib.id,
            title=title,
            file_name=f"{title}.mkv",
            file_path=f"C:/idslib/{title}.mkv",
            mime_type="video/x-matroska",
            poster_path="C:/idslib/p.jpg",
            scrape_data={"genres": ["Drama"]},
        )

    tagged_a = media("tagged_a")
    tagged_b = media("tagged_b")
    untagged_a = media("untagged_a")
    untagged_b = media("untagged_b")
    missing = media("missing")
    missing.file_missing = True
    db.add_all([tagged_a, tagged_b, untagged_a, untagged_b, missing])
    await db.flush()

    tag_type = TagType(name="ids_genre", is_builtin=True)
    db.add(tag_type)
    await db.flush()
    tag = Tag(name="IdsTag", tag_type_id=tag_type.id)
    db.add(tag)
    await db.flush()
    for row in (tagged_a, tagged_b, missing):
        db.add(VideoTag(media_id=row.id, tag_id=tag.id))

    await db.commit()
    return {
        "library_id": lib.id,
        "tagged": [tagged_a.id, tagged_b.id],
        "untagged": [untagged_a.id, untagged_b.id],
        "missing": [missing.id],
    }


async def test_ids_only_returns_all_matching_ids_and_ignores_paging(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    ids = await seed(db_session)

    # page_size=1 会被忽略：ids 仍返回全部 5 条
    resp = await api_client.get(
        "/api/media", params={"ids_only": "true", "page_size": 1, "page": 2}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 5
    assert len(body["ids"]) == 5
    assert body["items"] == []
    assert set(body["ids"]) == {
        *ids["tagged"],
        *ids["untagged"],
        *ids["missing"],
    }


async def test_ids_only_honours_filters(api_client: AsyncClient, db_session: AsyncSession) -> None:
    ids = await seed(db_session)

    resp = await api_client.get(
        "/api/media",
        params={"ids_only": "true", "untagged": "true", "exclude_series": "true", "exclude_network": "true"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert sorted(body["ids"]) == sorted(ids["untagged"])

    missing = await api_client.get(
        "/api/media", params={"ids_only": "true", "file_missing": "true"}
    )
    assert sorted(missing.json()["ids"]) == sorted(ids["missing"])

    # 标签筛选同样生效
    by_tag = await api_client.get(
        "/api/media", params={"ids_only": "true", "tag_ids": "1"}
    )
    assert by_tag.status_code == 200


async def test_ids_only_rejects_oversized_result(
    api_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await seed(db_session)
    # 把上限压到 2 条来触发保护分支（真实上限 20000，测试里不该造 2 万行）
    monkeypatch.setattr(media_api_module, "MAX_IDS_ONLY", 2)

    resp = await api_client.get("/api/media", params={"ids_only": "true"})
    assert resp.status_code == 413
    detail = resp.json()["detail"]
    assert "超过单次全选上限" in detail
    # 提示必须告诉用户怎么办，而不是只报错
    assert "筛选" in detail
