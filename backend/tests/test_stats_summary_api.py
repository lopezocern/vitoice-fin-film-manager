"""Stats summary endpoint tests — issue-oriented counts and library health."""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import LibraryType, MediaType, ScrapeMode
from app.models.library import MediaLibrary
from app.models.media import Media
from app.models.series import Series


async def seed_stats(db: AsyncSession) -> dict[str, int]:
    visible = MediaLibrary(
        name="Visible",
        type=LibraryType.VIDEO,
        root_path="C:/media",
        scrape_mode=ScrapeMode.MOVIE,
        is_restricted=False,
    )
    restricted = MediaLibrary(
        name="Restricted",
        type=LibraryType.VIDEO,
        root_path="C:/restricted",
        scrape_mode=ScrapeMode.AV,
        is_restricted=True,
    )
    db.add_all([visible, restricted])
    await db.flush()

    show = Series(library_id=visible.id, title="A Show", episode_count=2)
    db.add(show)
    await db.flush()

    healthy = Media(
        library_id=visible.id,
        title="Healthy",
        file_name="healthy.mkv",
        file_path="C:/media/healthy.mkv",
        mime_type="video/x-matroska",
        file_size=100,
        poster_path="C:/media/healthy.jpg",
        thumbnail_path="C:/media/healthy-thumb.jpg",
        scrape_data={"genres": ["Drama"]},
    )
    missing = Media(
        library_id=visible.id,
        title="Missing",
        file_name="missing.mkv",
        file_path="C:/media/missing.mkv",
        mime_type="video/x-matroska",
        file_size=50,
        file_missing=True,
    )
    no_poster = Media(
        library_id=visible.id,
        title="No Poster",
        file_name="no-poster.mkv",
        file_path="C:/media/no-poster.mkv",
        mime_type="video/x-matroska",
        file_size=30,
        scrape_data={"genres": ["SciFi"]},
    )
    episode = Media(
        library_id=visible.id,
        series_id=show.id,
        title="Episode 1",
        file_name="s01e01.mp4",
        file_path="C:/media/s01e01.mp4",
        mime_type="video/mp4",
        file_size=20,
    )
    net = Media(
        library_id=visible.id,
        title="Net Only",
        file_name="net.mkv",
        file_path="",
        mime_type="video/x-matroska",
        file_size=0,
        media_type=MediaType.NETWORK,
    )
    hidden = Media(
        library_id=restricted.id,
        title="Hidden Missing",
        file_name="hidden.mkv",
        file_path="C:/restricted/hidden.mkv",
        mime_type="video/x-matroska",
        file_size=10,
        file_missing=True,
    )
    db.add_all([healthy, missing, no_poster, episode, net, hidden])
    await db.commit()
    return {
        "healthy": healthy.id,
        "missing": missing.id,
        "no_poster": no_poster.id,
        "episode": episode.id,
        "hidden": hidden.id,
        "net": net.id,
    }


async def test_stats_summary_issue_counts(api_client: AsyncClient, db_session: AsyncSession) -> None:
    await seed_stats(db_session)
    resp = await api_client.get("/api/stats/summary")
    assert resp.status_code == 200
    data = resp.json()
    summary = data["summary"]

    # visible library: healthy + missing + no_poster + episode + net = 5 visible media
    assert summary["media_count"] == 5
    # missing visible only (hidden restricted is filtered when show_restricted=false)
    assert summary["missing_count"] == 1
    # no poster: missing + no_poster + episode all lack poster, but episodes are excluded
    assert summary["no_poster_count"] == 2
    # no metadata: only `missing` lacks scrape_data (no_poster has it); episodes excluded
    assert summary["no_metadata_count"] == 1
    # 来源统计：healthy + no_poster + episode 为可用本地文件（missing 因 file_missing 排除）；
    # net 为网络媒体
    assert summary["local_count"] == 3  # healthy + no_poster + episode
    assert summary["network_count"] == 1  # net

    # library health: only the visible library is exposed
    libraries = data["library_health"]
    assert len(libraries) == 1
    entry = libraries[0]
    assert entry["name"] == "Visible"
    assert entry["media_count"] == 5
    assert entry["missing_count"] == 1
    assert entry["total_size"] == 200  # 100 + 50 + 30 + 20 + 0(net)


async def test_stats_summary_restricted_library_included_when_visible(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    await seed_stats(db_session)
    # Show restricted content so the restricted library participates.
    from app.models.enums import SettingType
    from app.models.setting import Setting

    db_session.add(Setting(key="show_restricted", value="true", type=SettingType.BOOL))
    await db_session.commit()
    resp = await api_client.get("/api/stats/summary")
    assert resp.status_code == 200
    data = resp.json()

    assert data["summary"]["media_count"] == 6
    assert data["summary"]["missing_count"] == 2
    assert data["summary"]["local_count"] == 3
    assert data["summary"]["network_count"] == 1

    names = {entry["name"] for entry in data["library_health"]}
    assert names == {"Visible", "Restricted"}
