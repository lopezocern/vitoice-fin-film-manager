"""Regression tests for the media access gate (soft-delete + restricted).

Background
----------
Before 2026-09-02 the restricted-content switch and the recycle bin's
soft-delete flag were enforced only in ``api/media.py::_get_media_or_404``.
Nine other endpoints resolved media with a bare ``db.get(Media, id)``, so a
user who turned *off* "show restricted content" could still read subtitles,
segments, tags and media URLs of a restricted library by calling those
endpoints directly — and soft-deleted rows were reachable too.

The gate now lives in ``app/services/media_access.py::get_accessible_media``.
These tests pin that behaviour end-to-end over HTTP, because the bug was in
*which helper each endpoint called*, not in the helper itself — a unit test of
the helper would have passed all along.

Note the asserted status is always 404, never 403: a 403 would confirm the
row exists, leaking the very fact the restricted switch exists to hide.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library import MediaLibrary
from app.models.media import Media
from app.models.setting import Setting

pytestmark = pytest.mark.asyncio


async def _make_lib(
    db: AsyncSession, name: str, root: str, *, restricted: bool = False
) -> MediaLibrary:
    lib = MediaLibrary(name=name, root_path=root, is_restricted=restricted)
    db.add(lib)
    await db.flush()
    return lib


async def _make_media(
    db: AsyncSession, lib_id: int, title: str, *, deleted: bool = False
) -> Media:
    media = Media(
        title=title,
        file_path=f"/tmp/{title}.mp4",
        file_name=f"{title}.mp4",
        library_id=lib_id,
        is_deleted=deleted,
    )
    db.add(media)
    await db.flush()
    return media


async def _set_show_restricted(db: AsyncSession, value: str) -> None:
    await db.execute(
        Setting.__table__.delete().where(Setting.key == "show_restricted")
    )
    db.add(Setting(key="show_restricted", value=value))
    await db.flush()


# Endpoints that resolve a media by id and must all go through the gate.
GATED_ENDPOINTS = [
    ("get", "/api/media/{id}/subtitles"),
    ("get", "/api/media/{id}/segments"),
]


@pytest.fixture
async def fixture_data(db_session: AsyncSession):
    normal = await _make_lib(db_session, "normal", "/tmp/gate-normal")
    restricted = await _make_lib(
        db_session, "restricted", "/tmp/gate-restricted", restricted=True
    )
    visible = await _make_media(db_session, normal.id, "visible")
    hidden = await _make_media(db_session, restricted.id, "hidden")
    deleted = await _make_media(db_session, normal.id, "deleted", deleted=True)
    await db_session.flush()
    return {
        "normal_lib": normal,
        "restricted_lib": restricted,
        "visible": visible,
        "hidden": hidden,
        "deleted": deleted,
    }


@pytest.mark.parametrize(("method", "path_template"), GATED_ENDPOINTS)
async def test_restricted_media_is_invisible_when_switch_off(
    api_client: AsyncClient,
    db_session: AsyncSession,
    fixture_data: dict,
    method: str,
    path_template: str,
) -> None:
    """Restricted-library media must 404 on every gated endpoint."""
    await _set_show_restricted(db_session, "false")

    url = path_template.format(id=fixture_data["hidden"].id)
    response = await getattr(api_client, method)(url)

    assert response.status_code == 404, (
        f"{method.upper()} {url} returned {response.status_code} — the endpoint "
        "is resolving media without the restricted-content gate."
    )


@pytest.mark.parametrize(("method", "path_template"), GATED_ENDPOINTS)
async def test_restricted_media_is_visible_when_switch_on(
    api_client: AsyncClient,
    db_session: AsyncSession,
    fixture_data: dict,
    method: str,
    path_template: str,
) -> None:
    """Turning the switch on must re-expose the same media (no over-blocking)."""
    await _set_show_restricted(db_session, "true")

    url = path_template.format(id=fixture_data["hidden"].id)
    response = await getattr(api_client, method)(url)

    assert response.status_code == 200, (
        f"{method.upper()} {url} returned {response.status_code} with "
        "show_restricted=true — the gate is over-blocking."
    )


@pytest.mark.parametrize(("method", "path_template"), GATED_ENDPOINTS)
async def test_soft_deleted_media_is_invisible(
    api_client: AsyncClient,
    db_session: AsyncSession,
    fixture_data: dict,
    method: str,
    path_template: str,
) -> None:
    """Recycle-bin rows must not be reachable through the normal endpoints."""
    url = path_template.format(id=fixture_data["deleted"].id)
    response = await getattr(api_client, method)(url)

    assert response.status_code == 404, (
        f"{method.upper()} {url} returned {response.status_code} — soft-deleted "
        "media is reachable outside the recycle bin."
    )


@pytest.mark.parametrize(("method", "path_template"), GATED_ENDPOINTS)
async def test_plain_media_still_reachable(
    api_client: AsyncClient,
    fixture_data: dict,
    method: str,
    path_template: str,
) -> None:
    """The gate must not break the happy path."""
    url = path_template.format(id=fixture_data["visible"].id)
    response = await getattr(api_client, method)(url)

    assert response.status_code == 200
    assert response.json() == []


async def test_recycle_bin_can_still_see_deleted_media(
    api_client: AsyncClient,
    fixture_data: dict,
) -> None:
    """The recycle bin is the sanctioned exception — allow_deleted=True.

    If this starts 404ing, someone routed the recycle bin through the default
    gate and deleted media became unreachable for restore.
    """
    response = await api_client.get("/api/recycle-bin")

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert fixture_data["deleted"].id in ids, (
        "Soft-deleted media is missing from the recycle bin listing."
    )


async def test_tagging_restricted_media_is_rejected(
    api_client: AsyncClient,
    db_session: AsyncSession,
    fixture_data: dict,
) -> None:
    """Write paths must be gated too, not just reads."""
    await _set_show_restricted(db_session, "false")

    created = await api_client.post("/api/tags", json={"name": "gate-tag"})
    assert created.status_code == 201
    tag_id = created.json()["id"]

    # Send the real frontend payload ({tag_id} only): VideoTagCreate now
    # accepts a missing media_id (the handler derives it from the path), so
    # this must exercise the gate and return 404 — not a 422 from schema
    # validation.
    hidden_id = fixture_data["hidden"].id
    response = await api_client.post(
        f"/api/media/{hidden_id}/tags",
        json={"tag_id": tag_id},
    )

    assert response.status_code == 404, (
        f"Tagging restricted media returned {response.status_code} — the write "
        "path bypasses the gate."
    )


async def test_tag_media_accepts_tag_id_without_media_id(
    api_client: AsyncClient,
    fixture_data: dict,
) -> None:
    """Frontend sends only {tag_id}; the route must not 422 on media_id.

    Regression for the installed build: detail-page "add tags" always failed
    with "添加标签失败" because ``VideoTagCreate`` declared ``media_id`` as
    required while ``syncMediaTags`` POSTs ``{"tag_id": ...}`` only — Pydantic
    rejected the body before the handler could overwrite media_id from the path.
    """
    created = await api_client.post("/api/tags", json={"name": "reg-tag"})
    assert created.status_code == 201
    tag_id = created.json()["id"]

    mid = fixture_data["visible"].id
    response = await api_client.post(
        f"/api/media/{mid}/tags", json={"tag_id": tag_id}
    )

    assert response.status_code == 201, response.text
    assert response.json()["media_id"] == mid

    # Clean up the association (also exercises the untag endpoint).
    removed = await api_client.delete(f"/api/media/{mid}/tags/{tag_id}")
    assert removed.status_code == 204


async def test_batch_reports_per_item_failure_without_aborting(
    api_client: AsyncClient,
    db_session: AsyncSession,
    fixture_data: dict,
) -> None:
    """One inaccessible id must not abort the whole batch.

    `api/batch.py` previously aborted on the first failure; it now records a
    per-item failure so the remaining ids still get processed.
    """
    await _set_show_restricted(db_session, "false")

    response = await api_client.post(
        "/api/media/batch",
        json={
            "action": "metadata_ignore",
            "media_ids": [fixture_data["hidden"].id, fixture_data["visible"].id],
            "params": {"ignored": True},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()

    # BatchFailedItem is {id, error}
    failed_ids = [entry.get("id") for entry in body.get("failed") or []]
    assert fixture_data["hidden"].id in failed_ids, (
        f"Restricted media was not reported as a per-item failure: {body}"
    )
    assert body.get("success_count", 0) >= 1, (
        f"The batch aborted instead of processing the accessible id: {body}"
    )
