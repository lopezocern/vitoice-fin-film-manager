"""Shared predicates for media "issue" queries — single source of truth.

`/stats/summary` counts and `/media` filters must never drift: both go through
the helpers here, so a sidebar badge always equals the `total` of the list it
opens. Adding a new issue kind means adding one predicate here and reusing it
on both sides.

Scope note — an "issue" is only reported for rows a user can act on:

* soft-deleted rows (recycle bin) are out;
* TV episodes inherit poster/metadata from their parent series, so they are
  not individually incomplete;
* NETWORK-only media legitimately have no local file and no scraped poster.

The one deliberate exception is `pred_metadata_missing()`, which the metadata
workbench (and `no_metadata_count`) applies *without* `issue_scope()` — that
view has always included network media, and changing it would silently move
existing counts.
"""
from sqlalchemy import and_, exists, or_

from app.models.enums import MediaType
from app.models.media import Media, VideoTag

#: Values accepted by the `/media` `metadata_status` filter.
METADATA_STATUSES = ("missing", "ignored", "complete")


def issue_scope() -> list:
    """Conditions a row must satisfy to be reported as an issue."""
    return [
        Media.is_deleted == False,  # noqa: E712
        Media.series_id.is_(None),
        Media.media_type != MediaType.NETWORK,
    ]


def pred_missing():
    """Local file disappeared but the record was kept."""
    return Media.file_missing.is_(True)


def pred_no_poster():
    """Neither a scraped/user poster nor a generated thumbnail exists."""
    return and_(Media.poster_path.is_(None), Media.thumbnail_path.is_(None))


def pred_metadata_missing():
    """Scraped metadata is incomplete and the user has not opted out."""
    return and_(
        Media.metadata_ignored == False,  # noqa: E712
        or_(Media.poster_path.is_(None), Media.scrape_data.is_(None)),
    )


def pred_untagged():
    """No tag at all (uses the `ix_video_tags_media_id` index)."""
    return ~exists().where(VideoTag.media_id == Media.id)


def pred_problem():
    """Union of the issue predicates — never a sum.

    An item missing both its poster and its metadata must count once, which a
    simple `missing + no_poster + metadata` sum gets wrong.
    """
    return or_(pred_missing(), pred_no_poster(), pred_metadata_missing())
