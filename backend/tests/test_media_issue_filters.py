"""Guard rail: a Saved-View total must equal the stats badge that opens it.

Every assertion compares ``GET /media?...total`` with the matching field of
``GET /stats/summary``. If anyone hand-writes a predicate on one side only,
these tests fail — that is the entire point of ``services/media_query.py``.

The seed below is deliberately small and fully enumerated so the expected
numbers are *hard-coded* rather than recomputed from the same predicates under
test (which would be a tautology).

Seed rows (visible library, nothing soft-deleted unless noted):

    name         poster  scrape  tags  file_missing  others
    ---------------------------------------------------------------
    happy         yes     yes    yes       no
    missing       yes     yes    yes      YES
    no_poster      -      yes    yes       no
    no_meta       yes      -     yes       no
    untagged      yes     yes     -        no
    ignored        -       -     yes       no       metadata_ignored
    both           -       -     yes      YES
    episode        -      yes     yes       no       series_id set  (out of scope)
    network        -       -     yes      YES       media_type=NETWORK (out of scope)
    deleted        -       -     yes      YES       is_deleted      (out of scope)

Expected issue counts (scope = non-deleted, non-episode, non-NETWORK):
    missing 2 (missing, both) · no_poster 3 (no_poster, ignored, both)
    untagged 1 · problem(union) 5 · metadata_missing 4 (scope-free, incl. network)
    ignored 1 · sum(missing+no_poster+metadata) = 9 ≠ union 5  ← the double-count trap

Note on `scrape_data`: it is a JSON column, so an explicitly assigned Python
`None` persists as the JSON literal `null`, which `scrape_data IS NULL` does
not match. Rows are therefore seeded by *omitting* the column (a real SQL
NULL, matching production: dev DB has 27 SQL NULL and 0 JSON null).
"""
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import LibraryType, MediaType, ScrapeMode
from app.models.library import MediaLibrary
from app.models.media import Media
from app.models.series import Series
from app.models.tag import Tag, TagType, VideoTag

# Hard-coded expectations for the seed above.
EXPECTED_MISSING = 2
EXPECTED_NO_POSTER = 3
EXPECTED_UNTAGGED = 1
EXPECTED_PROBLEM = 5
EXPECTED_NO_METADATA = 4
EXPECTED_IGNORED = 1
EXPECTED_MEDIA_COUNT = 9  # non-deleted rows (stats excludes restricted libs)

#: Sentinel marking "caller did not mention scrape_data" (see `media()`).
_UNSET = object()


async def seed_issues(db: AsyncSession) -> dict[str, int]:
    lib = MediaLibrary(
        name="Issues",
        type=LibraryType.VIDEO,
        root_path="C:/issues",
        scrape_mode=ScrapeMode.MOVIE,
    )
    db.add(lib)
    await db.flush()

    show = Series(library_id=lib.id, title="Show", episode_count=1)
    db.add(show)
    await db.flush()

    def media(**kw) -> Media:
        base: dict = {
            "library_id": lib.id,
            "title": kw.pop("title"),
            "file_name": kw.pop("file_name"),
            "file_path": kw.pop("file_path", None),
            "mime_type": "video/x-matroska",
            "poster_path": kw.pop("poster_path", "C:/issues/p.jpg"),
            "thumbnail_path": None,
            "file_size": kw.pop("file_size", 1000),
        }
        # Attach `scrape_data` only when a payload is given. Passing an explicit
        # `scrape_data=None` would be persisted as the JSON literal `null`
        # (SQLAlchemy's JSON type default), which `scrape_data IS NULL` does NOT
        # match. Production rows that were never scraped hold a real SQL NULL
        # (dev DB: 27 SQL NULL, 0 JSON null), so omission is the realistic form.
        scrape = kw.pop("scrape_data", _UNSET)
        if scrape is not _UNSET:
            base["scrape_data"] = scrape
        base.update(kw)
        return Media(**base)

    rows = {
        "happy": media(
            title="happy", file_name="happy.mkv", file_path="C:/issues/happy.mkv",
            scrape_data={"genres": ["Drama"]},
        ),
        "missing": media(
            title="missing", file_name="missing.mkv",
            file_path="C:/issues/missing.mkv", file_missing=True,
            scrape_data={"genres": ["Drama"]},
        ),
        "no_poster": media(
            title="no_poster", file_name="nop.mkv",
            file_path="C:/issues/nop.mkv", poster_path=None,
            scrape_data={"genres": ["Drama"]},
        ),
        "no_meta": media(
            title="no_meta", file_name="nometa.mkv",
            file_path="C:/issues/nometa.mkv",
        ),
        "untagged": media(
            title="untagged", file_name="untagged.mkv",
            file_path="C:/issues/untagged.mkv",
            scrape_data={"genres": ["Drama"]},
        ),
        "ignored": media(
            title="ignored", file_name="ignored.mkv",
            file_path="C:/issues/ignored.mkv",
            poster_path=None, metadata_ignored=True,
        ),
        "both": media(
            title="both", file_name="both.mkv",
            file_path="C:/issues/both.mkv",
            poster_path=None, file_missing=True,
        ),
        "episode": media(
            title="ep", file_name="ep.mkv",
            file_path="C:/issues/ep.mkv", poster_path=None, series_id=show.id,
            scrape_data={"genres": ["Drama"]},
        ),
        "network": media(
            title="net", file_name="net",
            media_type=MediaType.NETWORK, poster_path=None,
            file_size=None, file_missing=True,
        ),
        "deleted": media(
            title="del", file_name="del.mkv",
            file_path="C:/issues/del.mkv", poster_path=None,
            file_missing=True, is_deleted=True,
        ),
    }
    db.add_all(rows.values())
    await db.flush()

    tag_type = TagType(name="genre", is_builtin=True)
    db.add(tag_type)
    await db.flush()
    tag = Tag(name="Drama", tag_type_id=tag_type.id)
    db.add(tag)
    await db.flush()

    # Everything is tagged except "untagged" and the episode (which is out of
    # scope anyway, so an untagged episode must not affect the count).
    for name, row in rows.items():
        if name in ("untagged", "episode"):
            continue
        db.add(VideoTag(media_id=row.id, tag_id=tag.id))

    await db.commit()
    return {"library_id": lib.id}


async def _total(client: AsyncClient, **params) -> int:
    resp = await client.get("/api/media", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["total"]


async def _summary(client: AsyncClient) -> dict:
    resp = await client.get("/api/stats/summary")
    assert resp.status_code == 200, resp.text
    return resp.json()["summary"]


# The seven Saved Views, exactly as `lib/media/views.ts` will build them.
SCOPE = {"exclude_series": True, "exclude_network": True}
VIEWS = {
    "missing": ({"file_missing": True, **SCOPE}, "missing_count", EXPECTED_MISSING),
    "no_poster": ({"has_poster": False, **SCOPE}, "no_poster_count", EXPECTED_NO_POSTER),
    "metadata": ({"metadata_status": "missing", "exclude_series": True}, "no_metadata_count", EXPECTED_NO_METADATA),
    "untagged": ({"untagged": True, **SCOPE}, "untagged_count", EXPECTED_UNTAGGED),
    "problem": ({"problem": True, **SCOPE}, "problem_count", EXPECTED_PROBLEM),
    "ignored": ({"metadata_status": "ignored"}, "ignored_count", EXPECTED_IGNORED),
}


async def test_each_saved_view_total_matches_its_stats_field(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    """The core invariant: badge number == list total, view by view."""
    await seed_issues(db_session)
    summary = await _summary(api_client)

    for view, (params, stats_key, expected) in VIEWS.items():
        total = await _total(api_client, **params)
        assert total == expected, f"{view}: seeded expectation moved? got {total}"
        assert total == summary[stats_key], (
            f"{view}: /media total ({total}) != stats.{stats_key} "
            f"({summary[stats_key]}) — the predicates have drifted"
        )


async def test_problem_is_a_union_not_a_sum(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`both` is file_missing AND poster-less AND metadata-less — count it once."""
    await seed_issues(db_session)
    summary = await _summary(api_client)

    naive_sum = summary["missing_count"] + summary["no_poster_count"] + summary["no_metadata_count"]
    assert naive_sum > summary["problem_count"], "seed should contain overlapping issues"
    assert summary["problem_count"] == EXPECTED_PROBLEM
    assert await _total(api_client, problem=True, **SCOPE) == EXPECTED_PROBLEM


async def test_issue_scope_excludes_episodes_network_and_deleted(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Each of the three excluded row kinds is missing a poster AND has a
    problem flag; none of them may inflate the counts."""
    await seed_issues(db_session)
    summary = await _summary(api_client)

    # Default listing still sees every non-deleted row, including episode and
    # network media — scope only applies to the issue predicates.
    assert await _total(api_client) == 10 - 1  # 10 seeded, 1 soft-deleted
    assert summary["media_count"] == EXPECTED_MEDIA_COUNT

    # "both" + "no_poster" + "ignored" are poster-less; the episode, the
    # network row and the deleted row must not add to that number.
    assert summary["no_poster_count"] == EXPECTED_NO_POSTER


async def test_metadata_status_complete_is_the_complement(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Within issue scope, every row is exactly one of complete / missing /
    ignored — `ignored` is a third state, not a subset of either."""
    await seed_issues(db_session)
    complete = await _total(api_client, metadata_status="complete", **SCOPE)
    missing = await _total(api_client, metadata_status="missing", **SCOPE)
    scoped_total = await _total(api_client, **SCOPE)

    # happy / missing / untagged have a poster and scraped data.
    assert complete == 3
    # no_poster / no_meta / both are incomplete and not ignored.
    assert missing == 3
    # The "ignored" row is neither: it opted out.
    assert scoped_total == 7
    assert complete + missing + 1 == scoped_total


async def test_untagged_false_returns_tagged_rows_only(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    await seed_issues(db_session)
    tagged = await _total(api_client, untagged=False, **SCOPE)
    untagged = await _total(api_client, untagged=True, **SCOPE)
    scoped_total = await _total(api_client, **SCOPE)

    assert untagged == EXPECTED_UNTAGGED
    assert tagged + untagged == scoped_total


async def test_metadata_status_rejects_unknown_values(api_client: AsyncClient) -> None:
    resp = await api_client.get("/api/media", params={"metadata_status": "bogus"})
    assert resp.status_code == 422


async def test_libraries_expose_health_aggregates(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    """The manage page's library-status view reads these three numbers."""
    ids = await seed_issues(db_session)

    resp = await api_client.get("/api/libraries")
    assert resp.status_code == 200, resp.text
    entry = next(item for item in resp.json() if item["id"] == ids["library_id"])

    # media_count keeps its pre-existing meaning: every row in the library,
    # soft-deleted ones included (9 live + 1 deleted), and the NETWORK row has
    # no file_size.
    assert entry["media_count"] == 10
    assert entry["total_size"] == 9000
    # missing: missing, both (in scope) + network, deleted (counted here on
    # purpose — this endpoint is a raw per-library tally, not issue scope)
    assert entry["missing_count"] == 4

    single = await api_client.get(f"/api/libraries/{ids['library_id']}")
    assert single.status_code == 200, single.text
    assert single.json()["media_count"] == entry["media_count"]
    assert single.json()["missing_count"] == entry["missing_count"]
    assert single.json()["total_size"] == entry["total_size"]
