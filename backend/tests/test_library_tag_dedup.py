"""Regression tests for library root_path dedup and idempotent tag creation.

Background
----------
``MediaLibrary.root_path`` had no unique constraint and ``create_library``
performed no duplicate check, so the same directory could be registered twice
and scanned into duplicate media rows. Likewise ``Tag.name`` had no constraint
and ``create_tag`` performed no lookup, so concurrent tagging flows created
duplicate tags.

Both are now constrained (migration 020) *and* checked in the API layer, because
a raw ``IntegrityError`` would surface as a 500 instead of a user-facing 409.

Two findings are pinned deliberately:

* Library matching is **normalized** (case- and separator-insensitive), not
  exact-string. Stored values predate normalization, so exact matching would
  produce false negatives.
* Tag uniqueness is on the **composite** ``(name, tag_type_id)``, not on
  ``name`` alone. The dev database had 18 groups of same-named tags, all
  cross-type (e.g. one performer tagged as both ``actor`` and ``av_actress``)
  — a single-column unique index would have been wrong.
"""
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag import Tag, TagType

pytestmark = pytest.mark.asyncio


@pytest.fixture
def media_dir(tmp_path: Path) -> Path:
    """A real directory — LibraryCreate validates that the path exists."""
    target = tmp_path / "media"
    target.mkdir()
    return target


async def _create_library(
    api_client: AsyncClient, name: str, root: Path
) -> dict:
    response = await api_client.post(
        "/api/libraries", json={"name": name, "root_path": str(root)}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_duplicate_root_path_is_rejected(
    api_client: AsyncClient, media_dir: Path
) -> None:
    first = await _create_library(api_client, "first", media_dir)

    response = await api_client.post(
        "/api/libraries", json={"name": "second", "root_path": str(media_dir)}
    )

    assert response.status_code == 409, (
        "Duplicate root_path was accepted — the same directory can be scanned "
        "twice into duplicate media rows."
    )
    assert first["name"] in response.json()["detail"]


async def test_duplicate_root_path_is_rejected_across_path_variants(
    api_client: AsyncClient, media_dir: Path
) -> None:
    """Case, separator style and trailing slash must not defeat dedup.

    Stored root_path values predate any normalization, so the check compares
    normalized forms rather than exact strings.
    """
    await _create_library(api_client, "first", media_dir)

    raw = str(media_dir)
    variants = [
        raw + "/",  # trailing slash
        raw + "\\",  # trailing backslash
        raw.replace("\\", "/"),  # forward slashes
        raw.upper(),  # case-folded
        raw.lower(),
        str(media_dir.resolve()) + "/./",  # redundant current-dir segment
    ]

    # Keep the name short: LibraryBase.name is capped at 100 chars and the
    # variants are long absolute paths.
    for index, variant in enumerate(variants):
        response = await api_client.post(
            "/api/libraries", json={"name": f"dup-{index}", "root_path": variant}
        )
        assert response.status_code == 409, (
            f"Path variant {variant!r} returned {response.status_code} "
            f"({response.text}) instead of 409"
        )


async def test_update_rejects_another_librarys_path(
    api_client: AsyncClient, tmp_path: Path
) -> None:
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()

    lib_a = await _create_library(api_client, "A", dir_a)
    await _create_library(api_client, "B", dir_b)

    response = await api_client.put(
        f"/api/libraries/{lib_a['id']}", json={"root_path": str(dir_b)}
    )

    assert response.status_code == 409, (
        "Updating a library onto another library's directory was accepted."
    )


async def test_update_accepts_its_own_unchanged_path(
    api_client: AsyncClient, media_dir: Path
) -> None:
    """exclude_id must prevent a library from colliding with itself.

    Without it, every PATCH that re-sends the current root_path (e.g. renaming
    a library with a full payload) would fail with a bogus 409.
    """
    lib = await _create_library(api_client, "A", media_dir)

    response = await api_client.put(
        f"/api/libraries/{lib['id']}",
        json={"name": "A-renamed", "root_path": str(media_dir)},
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "A-renamed"


async def test_same_name_different_type_creates_distinct_tags(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    """The composite key must not collapse cross-type homonyms.

    Real data has performers tagged as both `actor` and `av_actress`; a
    unique index on `name` alone would have rejected them.
    """
    type_a = await api_client.post("/api/tag-types", json={"name": "type-a"})
    type_b = await api_client.post("/api/tag-types", json={"name": "type-b"})
    assert type_a.status_code == 201 and type_b.status_code == 201

    first = await api_client.post(
        "/api/tags", json={"name": "performer", "tag_type_id": type_a.json()["id"]}
    )
    second = await api_client.post(
        "/api/tags", json={"name": "performer", "tag_type_id": type_b.json()["id"]}
    )

    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] != second.json()["id"], (
        "Same name under different tag types collapsed into one tag — the "
        "unique key is on `name` alone instead of (name, tag_type_id)."
    )


async def test_creating_the_same_tag_twice_is_idempotent(
    api_client: AsyncClient,
) -> None:
    """Returning the existing row keeps concurrent tagging flows from 500ing."""
    created = await api_client.post("/api/tags", json={"name": "repeat"})
    assert created.status_code == 201
    tag_id = created.json()["id"]

    again = await api_client.post("/api/tags", json={"name": "repeat"})

    assert again.status_code == 201, (
        "Re-creating an existing tag failed instead of returning it — tagging "
        "flows that race will surface this as a UI error."
    )
    assert again.json()["id"] == tag_id, (
        "Idempotent create returned a different id (no dedup happened)."
    )


async def test_unique_constraint_exists_at_the_database_layer(
    db_session: AsyncSession,
) -> None:
    """The API check is a courtesy; the DB constraint is the real guard."""
    tag_type = TagType(name="db-guard", is_builtin=False)
    db_session.add(tag_type)
    await db_session.flush()

    db_session.add(Tag(name="dup", tag_type_id=tag_type.id))
    await db_session.flush()

    rows = (
        await db_session.execute(
            select(Tag).where(Tag.name == "dup", Tag.tag_type_id == tag_type.id)
        )
    ).scalars().all()
    assert len(rows) == 1

    # A second identical row must be rejected by the database itself.
    db_session.add(Tag(name="dup", tag_type_id=tag_type.id))
    with pytest.raises(Exception) as exc_info:
        await db_session.flush()
    assert "UNIQUE" in str(exc_info.value).upper(), (
        f"Duplicate (name, tag_type_id) was accepted at the DB layer: {exc_info.value}"
    )
