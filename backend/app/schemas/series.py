"""Schemas for Series — TV show aggregation entity."""
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from app.schemas.common import ORMBaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""
    items: list[T]
    total: int
    page: int
    page_size: int


class SeriesCreate(BaseModel):
    """Schema for creating a series."""
    library_id: int
    title: str = Field(..., max_length=500)
    tmdb_id: int | None = None
    year: int | None = None
    overview: str | None = None
    poster_path: str | None = None
    scrape_data: dict[str, Any] | None = None
    total_seasons: int | None = None
    total_episodes: int | None = None


class SeriesUpdate(BaseModel):
    """Schema for updating a series — all fields optional."""
    title: str | None = Field(None, max_length=500)
    tmdb_id: int | None = None
    year: int | None = None
    overview: str | None = None
    poster_path: str | None = None
    scrape_data: dict[str, Any] | None = None
    total_seasons: int | None = None
    total_episodes: int | None = None
    episode_count: int | None = None
    sort_order: int | None = None


class SeriesResponse(ORMBaseModel):
    """Series response with aggregated stats."""
    id: int
    library_id: int
    title: str
    tmdb_id: int | None = None
    year: int | None = None
    overview: str | None = None
    poster_path: str | None = None
    scrape_data: dict[str, Any] | None = None
    total_seasons: int | None = None
    total_episodes: int | None = None
    episode_count: int = 0
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


class EpisodeResponse(ORMBaseModel):
    """Lightweight episode info for series detail page."""
    id: int
    title: str
    file_name: str
    season_number: int | None = None
    episode_number: int | None = None
    duration: float | None = None
    thumbnail_path: str | None = None
    poster_path: str | None = None
    rating: int | None = None
    is_favorite: bool = False
    is_watched: bool = False
    playback_position: float = 0.0
    file_size: int | None = None
    year: int | None = None


class SeasonGroup(BaseModel):
    """A season within a series — groups episodes by season number."""
    season_number: int
    episode_count: int
    episodes: list[EpisodeResponse]


class SeriesDetailResponse(SeriesResponse):
    """Series detail with episodes grouped by season."""
    seasons: list[SeasonGroup] = []
    unseasoned_episodes: list[EpisodeResponse] = []


class EpisodeNavigation(BaseModel):
    """Previous/next episode navigation for the detail page."""
    has_previous: bool = False
    has_next: bool = False
    previous_id: int | None = None
    next_id: int | None = None
    previous_title: str | None = None
    next_title: str | None = None
