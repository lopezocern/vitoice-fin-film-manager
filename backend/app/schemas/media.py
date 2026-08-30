"""Schemas for Media and MediaUrl."""
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import MediaType, UrlRole
from app.schemas.common import ORMBaseModel
from app.schemas.segment import SegmentResponse
from app.schemas.subtitle import SubtitleResponse
from app.schemas.tag import TagResponse
from app.schemas.series import SeriesResponse


class MediaUrlCreate(BaseModel):
    """Schema for creating a media URL."""
    url: str = Field(..., max_length=2000)
    url_role: UrlRole = UrlRole.REFERENCE
    title: str | None = Field(None, max_length=500)
    platform: str | None = Field(None, max_length=100)
    played_progress: float = 0.0
    is_expired: bool = False


class MediaUrlUpdate(BaseModel):
    """Schema for updating a media URL — all fields optional."""
    url: str | None = Field(None, max_length=2000)
    url_role: UrlRole | None = None
    title: str | None = Field(None, max_length=500)
    platform: str | None = Field(None, max_length=100)
    is_expired: bool | None = None


class MediaUrlResponse(ORMBaseModel):
    """Media URL response schema."""
    id: int
    media_id: int
    url: str
    url_role: UrlRole
    title: str | None = None
    platform: str | None = None
    last_visited_at: datetime | None = None
    played_progress: float = 0.0
    is_expired: bool = False
    created_at: datetime
    updated_at: datetime


class MediaBase(BaseModel):
    """Shared core fields for media."""
    title: str = Field(..., max_length=500)
    file_path: str | None = Field(None, max_length=1000)
    file_name: str = Field(..., max_length=500)
    media_type: MediaType = MediaType.LOCAL


class MediaCreate(MediaBase):
    """Schema for creating a media record."""
    library_id: int
    file_size: int | None = None
    file_hash: str | None = Field(None, max_length=64)
    mime_type: str | None = Field(None, max_length=100)
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    codec: str | None = Field(None, max_length=50)
    fps: float | None = None
    bitrate: int | None = None
    thumbnail_path: str | None = None
    poster_path: str | None = None
    file_modified_at: datetime | None = None


class MediaUpdate(BaseModel):
    """Schema for updating a media — all fields optional."""
    title: str | None = Field(None, max_length=500)
    year: int | None = None
    description: str | None = None
    release_date: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    rating: int | None = Field(None, ge=1, le=5)
    is_favorite: bool | None = None
    is_watched: bool | None = None
    playback_position: float | None = None
    playback_speed: float | None = None
    thumbnail_path: str | None = None
    poster_path: str | None = None
    library_id: int | None = None


class AITagSuggestion(BaseModel):
    """A single AI-generated tag suggestion returned by the ai-tags endpoint."""
    name: str
    type: str
    confidence: float


class AIRescrapeResponse(BaseModel):
    """Result of an AI-assisted rescrape attempt (POST /media/{id}/ai-rescrape).

    When the AI suggests a clean title/year and the retried TMDB search
    matches, ``success`` is True and ``matched_title``/``matched_year``
    hold the TMDB result. Otherwise ``success`` is False and ``message``
    explains why (e.g. no TMDB match).
    """
    success: bool
    suggested_title: str | None = None
    suggested_year: int | None = None
    matched_title: str | None = None
    matched_year: int | None = None
    message: str = ""


class PlaybackProgressUpdate(BaseModel):
    """Schema for updating playback progress."""
    position: float = Field(..., ge=0, description="Playback position in seconds")
    speed: float | None = None
    is_watched: bool | None = None


class ProgressResponse(BaseModel):
    """Lightweight response for progress update — avoids full MediaResponse serialization."""
    position: float
    is_watched: bool


class MediaRenameRequest(BaseModel):
    """Schema for renaming a media file on disk.

    The new_name should be just the filename (no directory path).
    The backend will preserve the file's current directory and only
    change the filename portion.
    """
    new_name: str = Field(..., min_length=1, max_length=500)
    re_scrape: bool = Field(False, description="Trigger re-scraping after rename")


class MediaResponse(ORMBaseModel):
    """Full media response — includes nested relations when loaded."""
    id: int
    library_id: int
    title: str
    file_path: str | None = None
    file_name: str
    media_type: MediaType
    file_size: int | None = None
    file_hash: str | None = None
    mime_type: str | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    codec: str | None = None
    fps: float | None = None
    bitrate: int | None = None
    thumbnail_path: str | None = None
    poster_path: str | None = None
    year: int | None = None
    release_date: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    series_id: int | None = None
    series_title: str | None = None
    scrape_data: dict[str, Any] | None = None
    description: str | None = None
    rating: int | None = None
    is_favorite: bool = False
    is_watched: bool = False
    metadata_ignored: bool = False
    playback_position: float = 0.0
    playback_speed: float | None = None
    last_played_at: datetime | None = None
    file_missing: bool = False
    missing_detected_at: datetime | None = None
    file_modified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    # Nested relations (populated when eagerly loaded; default to empty)
    urls: list[MediaUrlResponse] = []
    segments: list[SegmentResponse] = []
    tags: list[TagResponse] = []
    subtitles: list[SubtitleResponse] = []

    @field_validator("metadata_ignored", mode="before")
    @classmethod
    def _coerce_metadata_ignored(cls, v: Any) -> Any:
        """Treat legacy NULL columns as False (False default only fills missing)."""
        return False if v is None else v

    @field_validator("file_path", "thumbnail_path", "poster_path", mode="after")
    @classmethod
    def _mask_filesystem_paths(cls, v: str | None) -> str | None:
        """Mask filesystem paths to show only parent dir + filename.

        Prevents leaking the full server filesystem structure to the client.
        Short paths (≤2 components) are returned unchanged.
        """
        if not v:
            return v
        parts = Path(v).parts
        if len(parts) <= 2:
            return v
        return str(Path("...") / Path(*parts[-2:]))


class MediaListResponse(BaseModel):
    """Paginated media list response."""
    items: list[MediaResponse]
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


class MediaFacetItem(BaseModel):
    """A selectable media facet and its visible-media count."""
    value: str
    count: int


class MediaTagFacet(MediaFacetItem):
    id: int
    color: str | None = None


class MediaFacetsResponse(BaseModel):
    """Counts and options used by the media home page."""
    all: int = 0
    movies: int = 0
    series: int = 0
    episodes: int = 0
    images: int = 0
    audio: int = 0
    genres: list[MediaFacetItem] = []
    countries: list[MediaFacetItem] = []
    years: list[MediaFacetItem] = []
    tags: list[MediaTagFacet] = []


class MediaHomeItem(BaseModel):
    """One actionable item shown on the media watch center."""
    kind: Literal["media", "series"]
    data: MediaResponse | SeriesResponse


class MediaHomeResponse(BaseModel):
    """Action-oriented shelves for the media watch center."""
    continue_watching: list[MediaHomeItem] = []
    recently_added: list[MediaHomeItem] = []
    recently_played: list[MediaHomeItem] = []
    recommendations: list[MediaHomeItem] = []


class MediaFilter(BaseModel):
    """Filter / sort / pagination parameters for GET /media.

    Used as a dependency — fields are populated from query parameters.
    """
    library_id: int | None = None
    media_type: MediaType | None = None
    tag_ids: list[int] | None = None
    rating_min: int | None = Field(None, ge=1, le=5)
    duration_min: float | None = Field(None, description="Minimum duration in seconds")
    duration_max: float | None = Field(None, description="Maximum duration in seconds")
    resolution_min: int | None = Field(None, description="Minimum height in pixels")
    is_favorite: bool | None = None
    is_watched: bool | None = None
    search: str | None = None
    sort_by: str = "created_at"
    sort_order: str = "desc"
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=200)
