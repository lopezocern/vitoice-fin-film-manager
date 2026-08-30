from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import LibraryType, ScrapeMode
from app.models.library import MediaLibrary
from app.models.media import Media
from app.models.series import Series
from app.models.setting import Setting
from app.models.enums import SettingType
from app.models.tag import Tag, TagType, VideoTag


async def seed_media_home(db: AsyncSession) -> dict[str, int]:
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
    empty_show = Series(library_id=visible.id, title="Empty Show", episode_count=0)
    db.add_all([show, empty_show])
    await db.flush()

    movie = Media(
        library_id=visible.id,
        title="Movie",
        file_name="movie.mkv",
        file_path="C:/media/movie.mkv",
        mime_type="video/x-matroska",
        year=2024,
        scrape_data={"genres": ["Drama"], "production_countries": ["CN"]},
    )
    fallback_image = Media(
        library_id=visible.id,
        title="Photo",
        file_name="photo.webp",
        file_path="C:/media/photo.webp",
        mime_type=None,
        year=2023,
    )
    audio = Media(
        library_id=visible.id,
        title="Song",
        file_name="song.flac",
        file_path="C:/media/song.flac",
        mime_type="audio/flac",
    )
    episode_one = Media(
        library_id=visible.id,
        series_id=show.id,
        title="Episode 1",
        file_name="s01e01.mp4",
        file_path="C:/media/s01e01.mp4",
        mime_type="video/mp4",
    )
    episode_two = Media(
        library_id=visible.id,
        series_id=show.id,
        title="Episode 2",
        file_name="s01e02.mp4",
        file_path="C:/media/s01e02.mp4",
        mime_type="video/mp4",
    )
    deleted = Media(
        library_id=visible.id,
        title="Deleted",
        file_name="deleted.mp4",
        file_path="C:/media/deleted.mp4",
        mime_type="video/mp4",
        is_deleted=True,
    )
    hidden = Media(
        library_id=restricted.id,
        title="Hidden",
        file_name="hidden.mp4",
        file_path="C:/restricted/hidden.mp4",
        mime_type="video/mp4",
    )
    db.add_all([movie, fallback_image, audio, episode_one, episode_two, deleted, hidden])
    await db.flush()

    tag_type = TagType(name="Custom")
    db.add(tag_type)
    await db.flush()
    favorite = Tag(name="Favorite Tag", tag_type_id=tag_type.id, color="#ff0000")
    reviewed = Tag(name="Reviewed", tag_type_id=tag_type.id)
    db.add_all([favorite, reviewed])
    await db.flush()
    db.add_all([
        VideoTag(media_id=movie.id, tag_id=favorite.id),
        VideoTag(media_id=movie.id, tag_id=reviewed.id),
        VideoTag(media_id=audio.id, tag_id=favorite.id),
        VideoTag(media_id=hidden.id, tag_id=favorite.id),
    ])
    await db.commit()
    return {
        "favorite": favorite.id,
        "reviewed": reviewed.id,
        "movie": movie.id,
        "episode": episode_one.id,
        "hidden": hidden.id,
    }


async def test_media_home_groups_exclude_restricted_content(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    ids = await seed_media_home(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    movie = await db_session.get(Media, ids["movie"])
    episode = await db_session.get(Media, ids["episode"])
    hidden = await db_session.get(Media, ids["hidden"])
    assert movie and episode and hidden
    movie.duration = 7200
    movie.playback_position = 1200
    movie.last_played_at = now - timedelta(hours=2)
    episode.duration = 2700
    episode.playback_position = 900
    episode.last_played_at = now
    hidden.duration = 3600
    hidden.playback_position = 600
    hidden.last_played_at = now + timedelta(hours=1)
    await db_session.commit()

    response = await api_client.get("/api/media/home")

    assert response.status_code == 200
    body = response.json()
    continue_ids = [item["data"]["id"] for item in body["continue_watching"]]
    played_ids = [item["data"]["id"] for item in body["recently_played"]]
    all_library_ids = {
        item["data"]["library_id"]
        for shelf in body.values()
        for item in shelf
    }
    assert continue_ids[:2] == [ids["episode"], ids["movie"]]
    assert played_ids[:2] == [ids["episode"], ids["movie"]]
    assert ids["hidden"] not in continue_ids
    assert len(all_library_ids) == 1


async def test_media_home_recommendations_only_movies_and_series(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    await seed_media_home(db_session)

    response = await api_client.get("/api/media/home", params={"recommendation_seed": 2})

    assert response.status_code == 200
    recommendations = response.json()["recommendations"]
    assert recommendations
    assert {item["kind"] for item in recommendations} <= {"media", "series"}
    for item in recommendations:
        if item["kind"] == "media":
            assert item["data"]["series_id"] is None
            assert item["data"]["mime_type"].startswith("video")


async def test_progress_update_records_last_played_time(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    ids = await seed_media_home(db_session)
    before = datetime.now(timezone.utc).replace(tzinfo=None)

    response = await api_client.post(
        f'/api/media/{ids["movie"]}/progress', json={"position": 42}
    )

    assert response.status_code == 200
    db_session.expire_all()
    media = await db_session.get(Media, ids["movie"])
    assert media and media.last_played_at is not None
    assert media.last_played_at >= before


async def test_facets_use_visible_media_and_series_aggregation(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    await seed_media_home(db_session)

    response = await api_client.get("/api/media/facets")

    assert response.status_code == 200
    body = response.json()
    assert body["all"] == 4
    assert body["movies"] == 1
    assert body["series"] == 1
    assert body["episodes"] == 2
    assert body["images"] == 1
    assert body["audio"] == 1
    assert body["genres"] == [{"value": "Drama", "count": 1}]
    assert body["countries"] == [{"value": "CN", "count": 1}]
    assert body["years"] == [
        {"value": "2024", "count": 1},
        {"value": "2023", "count": 1},
    ]
    assert body["tags"][0]["value"] == "Favorite Tag"
    assert body["tags"][0]["count"] == 2


async def test_tag_matching_keeps_any_default_and_supports_all(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    ids = await seed_media_home(db_session)
    tag_ids = f'{ids["favorite"]},{ids["reviewed"]}'

    any_response = await api_client.get("/api/media", params={"tag_ids": tag_ids})
    all_response = await api_client.get(
        "/api/media", params={"tag_ids": tag_ids, "tag_match": "all"}
    )

    assert any_response.status_code == 200
    assert any_response.json()["total"] == 2
    assert all_response.status_code == 200
    assert all_response.json()["total"] == 1
    assert all_response.json()["items"][0]["id"] == ids["movie"]


async def test_series_and_content_type_filters(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    await seed_media_home(db_session)

    episodes = await api_client.get("/api/media", params={"has_series": True})
    standalone = await api_client.get("/api/media", params={"has_series": False})
    images = await api_client.get("/api/media", params={"content_type": "image"})

    assert episodes.status_code == 200
    assert episodes.json()["total"] == 2
    assert standalone.status_code == 200
    assert standalone.json()["total"] == 3
    assert images.status_code == 200
    assert images.json()["total"] == 1
    assert images.json()["items"][0]["title"] == "Photo"


async def test_invalid_tag_ids_return_validation_error(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/media", params={"tag_ids": "1,bad"})
    assert response.status_code == 422
    assert response.json()["detail"] == "tag_ids must contain integers"


async def test_facets_limit_quick_tags(api_client: AsyncClient, db_session: AsyncSession) -> None:
    ids = await seed_media_home(db_session)
    tag_type_id = (
        await db_session.get(Tag, ids["favorite"])
    ).tag_type_id
    movie_id = ids["movie"]
    for index in range(30):
        tag = Tag(name=f"Extra {index:02d}", tag_type_id=tag_type_id)
        db_session.add(tag)
        await db_session.flush()
        db_session.add(VideoTag(media_id=movie_id, tag_id=tag.id))
    await db_session.commit()

    response = await api_client.get("/api/media/facets")

    assert response.status_code == 200
    assert len(response.json()["tags"]) == 24


async def test_series_cross_library_view_merges_metadata_and_episodes(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    first_library = MediaLibrary(
        name="TV A", type=LibraryType.VIDEO, root_path="C:/tv-a",
        scrape_mode=ScrapeMode.TV, is_restricted=False,
    )
    second_library = MediaLibrary(
        name="TV B", type=LibraryType.VIDEO, root_path="C:/tv-b",
        scrape_mode=ScrapeMode.TV, is_restricted=False,
    )
    db_session.add_all([first_library, second_library])
    await db_session.flush()
    scraped = Series(
        library_id=first_library.id,
        title="The Show",
        tmdb_id=123,
        year=2020,
        overview="Scraped overview",
        poster_path="C:/posters/the-show.jpg",
        scrape_data={"genres": ["Drama"]},
        total_seasons=3,
        total_episodes=30,
        episode_count=2,
    )
    scanned = Series(
        library_id=second_library.id,
        title="The Show",
        episode_count=2,
    )
    db_session.add_all([scraped, scanned])
    await db_session.flush()
    db_session.add_all([
        Media(
            library_id=first_library.id, series_id=scraped.id, title="Episode 1",
            file_name="s01e01.mkv", season_number=1, episode_number=1,
        ),
        Media(
            library_id=first_library.id, series_id=scraped.id, title="Episode 2",
            file_name="s01e02.mkv", season_number=1, episode_number=2,
        ),
        Media(
            library_id=second_library.id, series_id=scanned.id, title="Duplicate 2",
            file_name="copy-s01e02.mkv", season_number=1, episode_number=2,
        ),
        Media(
            library_id=second_library.id, series_id=scanned.id, title="Episode 3",
            file_name="s02e01.mkv", season_number=2, episode_number=1,
        ),
    ])
    await db_session.commit()

    listing = await api_client.get("/api/series")
    detail = await api_client.get(f"/api/series/{scraped.id}")
    alias_detail = await api_client.get(f"/api/series/{scanned.id}")
    facets = await api_client.get("/api/media/facets")
    library_listing = await api_client.get(
        "/api/series", params={"library_id": second_library.id}
    )

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    item = listing.json()["items"][0]
    assert item["id"] == scraped.id
    assert item["tmdb_id"] == 123
    assert item["overview"] == "Scraped overview"
    assert item["episode_count"] == 3
    assert detail.status_code == 200
    assert detail.json()["episode_count"] == 3
    assert [(season["season_number"], season["episode_count"]) for season in detail.json()["seasons"]] == [(1, 2), (2, 1)]
    assert alias_detail.json()["id"] == scraped.id
    assert facets.json()["series"] == 1
    assert facets.json()["all"] == 1
    assert library_listing.json()["total"] == 1
    assert library_listing.json()["items"][0]["id"] == scanned.id
    assert library_listing.json()["items"][0]["library_id"] == second_library.id
    assert library_listing.json()["items"][0]["tmdb_id"] == 123
    assert library_listing.json()["items"][0]["poster_path"] == "C:/posters/the-show.jpg"
    assert library_listing.json()["items"][0]["episode_count"] == 2


async def test_series_view_excludes_restricted_and_separates_remakes(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    visible = MediaLibrary(
        name="Visible TV", type=LibraryType.VIDEO, root_path="C:/visible-tv",
        scrape_mode=ScrapeMode.TV, is_restricted=False,
    )
    hidden = MediaLibrary(
        name="Hidden TV", type=LibraryType.VIDEO, root_path="C:/hidden-tv",
        scrape_mode=ScrapeMode.TV, is_restricted=True,
    )
    db_session.add_all([visible, hidden])
    await db_session.flush()
    original = Series(library_id=visible.id, title="Same Name", tmdb_id=1, year=2001, episode_count=1)
    remake = Series(library_id=visible.id, title="Same Name", tmdb_id=2, year=2024, episode_count=1)
    restricted = Series(library_id=hidden.id, title="Hidden Show", episode_count=1)
    db_session.add_all([original, remake, restricted])
    await db_session.flush()
    db_session.add_all([
        Media(library_id=visible.id, series_id=original.id, title="Old", file_name="old.mkv", season_number=1, episode_number=1),
        Media(library_id=visible.id, series_id=remake.id, title="New", file_name="new.mkv", season_number=1, episode_number=1),
        Media(library_id=hidden.id, series_id=restricted.id, title="Hidden", file_name="hidden.mkv", season_number=1, episode_number=1),
    ])
    await db_session.commit()

    listing = await api_client.get("/api/series")
    hidden_detail = await api_client.get(f"/api/series/{restricted.id}")

    assert listing.status_code == 200
    assert listing.json()["total"] == 2
    assert {item["year"] for item in listing.json()["items"]} == {2001, 2024}
    assert hidden_detail.status_code == 404


async def test_inactive_scraped_series_can_supply_metadata_to_active_alias(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    metadata_library = MediaLibrary(
        name="Metadata TV", type=LibraryType.VIDEO, root_path="C:/metadata-tv",
        scrape_mode=ScrapeMode.TV, is_restricted=False,
    )
    active_library = MediaLibrary(
        name="Active TV", type=LibraryType.VIDEO, root_path="C:/active-tv",
        scrape_mode=ScrapeMode.TV, is_restricted=False,
    )
    db_session.add_all([metadata_library, active_library])
    await db_session.flush()
    metadata = Series(
        library_id=metadata_library.id, title="Metadata Show", tmdb_id=777,
        year=2022, overview="Useful metadata", poster_path="C:/poster.jpg",
        episode_count=0,
    )
    active = Series(library_id=active_library.id, title="Metadata Show", episode_count=1)
    empty = Series(library_id=metadata_library.id, title="Truly Empty", tmdb_id=888, episode_count=4)
    db_session.add_all([metadata, active, empty])
    await db_session.flush()
    db_session.add(Media(
        library_id=active_library.id, series_id=active.id, title="Episode 1",
        file_name="s01e01.mkv", season_number=1, episode_number=1,
    ))
    await db_session.commit()

    listing = await api_client.get("/api/series")
    detail = await api_client.get(f"/api/series/{active.id}")

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == active.id
    assert listing.json()["items"][0]["library_id"] == active_library.id
    assert listing.json()["items"][0]["tmdb_id"] == 777
    assert listing.json()["items"][0]["episode_count"] == 1
    assert detail.status_code == 200
    assert detail.json()["id"] == active.id
    assert detail.json()["library_id"] == active_library.id
    assert detail.json()["overview"] == "Useful metadata"


async def test_restricted_metadata_alias_does_not_mask_visible_series(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    restricted = MediaLibrary(
        name="Restricted Metadata", type=LibraryType.VIDEO, root_path="C:/restricted-meta",
        scrape_mode=ScrapeMode.AV, is_restricted=True,
    )
    visible = MediaLibrary(
        name="Visible TV", type=LibraryType.VIDEO, root_path="C:/visible-show",
        scrape_mode=ScrapeMode.TV, is_restricted=False,
    )
    db_session.add_all([restricted, visible])
    await db_session.flush()
    metadata = Series(
        library_id=restricted.id, title="Shared Show", tmdb_id=42,
        poster_path="C:/poster.jpg", overview="Useful metadata",
    )
    active = Series(library_id=visible.id, title="Shared Show", episode_count=1)
    db_session.add_all([metadata, active])
    await db_session.flush()
    db_session.add_all([
        Media(
            library_id=visible.id, series_id=active.id, title="Episode 1",
            file_name="s01e01.mkv", season_number=1, episode_number=1,
        ),
        Setting(
            key="show_restricted", value="true", type=SettingType.BOOL,
            category="general",
        ),
    ])
    await db_session.commit()

    listing = await api_client.get("/api/series")
    detail = await api_client.get(f"/api/series/{active.id}")

    assert listing.status_code == 200
    item = listing.json()["items"][0]
    assert item["id"] == active.id
    assert item["library_id"] == visible.id
    assert item["poster_path"] == "C:/poster.jpg"
    assert detail.status_code == 200
    assert detail.json()["id"] == active.id
    assert detail.json()["library_id"] == visible.id


async def test_hidden_restricted_alias_can_only_supply_series_metadata(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    restricted = MediaLibrary(
        name="Hidden Metadata", type=LibraryType.VIDEO, root_path="C:/hidden-meta",
        scrape_mode=ScrapeMode.AV, is_restricted=True,
    )
    visible = MediaLibrary(
        name="Visible Episodes", type=LibraryType.VIDEO, root_path="C:/visible-episodes",
        scrape_mode=ScrapeMode.TV, is_restricted=False,
    )
    db_session.add_all([restricted, visible])
    await db_session.flush()
    metadata = Series(
        library_id=restricted.id, title="Poster Show", tmdb_id=99,
        poster_path="C:/borrowed-poster.jpg", overview="Borrowed metadata",
    )
    active = Series(library_id=visible.id, title="Poster Show", episode_count=1)
    db_session.add_all([metadata, active])
    await db_session.flush()
    db_session.add(Media(
        library_id=visible.id, series_id=active.id, title="Episode 1",
        file_name="s01e01.mkv", season_number=1, episode_number=1,
    ))
    await db_session.commit()

    listing = await api_client.get("/api/series")
    detail = await api_client.get(f"/api/series/{active.id}")

    assert listing.status_code == 200
    item = listing.json()["items"][0]
    assert item["id"] == active.id
    assert item["library_id"] == visible.id
    assert item["poster_path"] == "C:/borrowed-poster.jpg"
    assert detail.status_code == 200
    assert detail.json()["poster_path"] == "C:/borrowed-poster.jpg"
