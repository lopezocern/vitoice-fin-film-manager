"""Build the cross-library Series view without changing stored ownership."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from app.models.media import Media
from app.models.series import Series
from app.schemas.series import SeriesResponse


def normalize_series_title(title: str) -> str:
    """Normalize display-title differences used by scanners and scrapers."""
    value = unicodedata.normalize("NFKC", title).casefold().strip()
    return re.sub(r"[\W_]+", "", value)


def group_equivalent_series(series_items: Iterable[Series]) -> list[list[Series]]:
    """Group the same show across libraries while keeping remakes separate."""
    by_title: dict[str, list[Series]] = {}
    for item in series_items:
        by_title.setdefault(normalize_series_title(item.title), []).append(item)

    groups: list[list[Series]] = []
    for title_items in by_title.values():
        tmdb_groups: dict[int, list[Series]] = {}
        unresolved: list[Series] = []
        for item in title_items:
            if item.tmdb_id is not None:
                tmdb_groups.setdefault(item.tmdb_id, []).append(item)
            else:
                unresolved.append(item)

        title_groups = list(tmdb_groups.values())
        for item in unresolved:
            compatible = [
                group
                for group in title_groups
                if not _has_conflicting_year(group, item.year)
            ]
            if len(compatible) == 1:
                compatible[0].append(item)
                continue

            same_year = next(
                (
                    group
                    for group in title_groups
                    if not any(member.tmdb_id is not None for member in group)
                    and _group_year(group) == item.year
                ),
                None,
            )
            if same_year is not None:
                same_year.append(item)
            else:
                title_groups.append([item])
        groups.extend(title_groups)
    return groups


def choose_representative(group: Iterable[Series]) -> Series:
    """Choose the record with the richest stable metadata for display."""
    return max(group, key=_metadata_score)


def choose_content_owner(group: Iterable[Series], episodes: Iterable[Media]) -> Series:
    """Choose identity from a Series that actually owns visible episodes.

    A metadata-only alias may have a richer poster but its library must never
    determine content restriction or navigation for episodes stored elsewhere.
    """
    episode_series_ids = {episode.series_id for episode in episodes}
    active = [item for item in group if item.id in episode_series_ids]
    return choose_representative(active or group)


def aggregate_series_response(group: list[Series], episodes: Iterable[Media]) -> SeriesResponse:
    episode_list = list(episodes)
    metadata = choose_representative(group)
    owner = choose_content_owner(group, episode_list)
    response = SeriesResponse.model_validate(metadata)
    response.id = owner.id
    response.library_id = owner.library_id
    response.sort_order = owner.sort_order
    response.created_at = owner.created_at
    response.updated_at = owner.updated_at
    response.episode_count = len(deduplicate_episodes(episode_list, owner.library_id))
    return response


def enrich_library_series_response(
    identity: Series,
    metadata_group: list[Series],
    episodes: Iterable[Media],
) -> SeriesResponse:
    """Keep library ownership while borrowing richer metadata from an alias."""
    response = SeriesResponse.model_validate(choose_representative(metadata_group))
    response.id = identity.id
    response.library_id = identity.library_id
    response.sort_order = identity.sort_order
    response.created_at = identity.created_at
    response.updated_at = identity.updated_at
    response.episode_count = len(deduplicate_episodes(episodes, identity.library_id))
    return response


def deduplicate_episodes(episodes: Iterable[Media], preferred_library_id: int) -> list[Media]:
    """Return one playable record for each season/episode coordinate."""
    ordered = sorted(
        episodes,
        key=lambda episode: (
            0 if episode.library_id == preferred_library_id else 1,
            -_episode_metadata_score(episode),
            episode.id,
        ),
    )
    selected: dict[tuple[object, ...], Media] = {}
    for episode in ordered:
        if episode.season_number is not None and episode.episode_number is not None:
            key: tuple[object, ...] = (
                "numbered",
                episode.season_number,
                episode.episode_number,
            )
        else:
            # Unnumbered files cannot be safely merged merely because names resemble.
            key = ("media", episode.id)
        selected.setdefault(key, episode)
    return sorted(selected.values(), key=_episode_sort_key)


def _metadata_score(item: Series) -> tuple[int, ...]:
    return (
        int(item.tmdb_id is not None),
        int(bool(item.poster_path)),
        int(bool(item.overview)),
        int(bool(item.scrape_data)),
        int(item.year is not None),
        int(item.total_seasons is not None),
        int(item.total_episodes is not None),
        item.episode_count or 0,
        -item.id,
    )


def _episode_metadata_score(item: Media) -> int:
    return sum(
        (
            bool(item.title),
            bool(item.poster_path),
            bool(item.thumbnail_path),
            bool(item.scrape_data),
            item.duration is not None,
            item.file_size is not None,
        )
    )


def _episode_sort_key(item: Media) -> tuple[int, int, int, str]:
    return (
        item.season_number if item.season_number is not None else 1_000_000,
        item.episode_number if item.episode_number is not None else 1_000_000,
        item.id,
        item.file_name,
    )


def _group_year(group: list[Series]) -> int | None:
    years = {item.year for item in group if item.year is not None}
    return next(iter(years)) if len(years) == 1 else None


def _has_conflicting_year(group: list[Series], year: int | None) -> bool:
    if year is None:
        return False
    years = {item.year for item in group if item.year is not None}
    return bool(years and year not in years)
