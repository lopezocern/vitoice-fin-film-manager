"""Media and MediaUrl models.

MediaUrl uses url_role to distinguish:
- source: playable/downloadable URL
- reference: link-only URL for source tracing

Local type media cannot have a `source` URL (other than the local file) to
maintain the local file as the sole playback source. All media types can have
reference URLs.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import MediaType, UrlRole, enum_values


class Media(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    library_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("media_libraries.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Core identity
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)  # null for network-only
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)

    # Type
    media_type: Mapped[MediaType] = mapped_column(
        Enum(MediaType, values_callable=enum_values), default=MediaType.LOCAL, nullable=False
    )

    # File metadata
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)  # bytes
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 64KB hash
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Media metadata (ffprobe)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)  # seconds
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    codec: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    bitrate: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Thumbnail
    thumbnail_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    poster_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Scraped metadata (TMDB)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    release_date: Mapped[str | None] = mapped_column(String(20), nullable=True)  # YYYY-MM-DD
    season_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Full scrape payload (tagline, vote_average, runtime, cast, countries, etc.)
    scrape_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Series aggregation — series_id links to a Series entity (set during
    # aggregation/scraping). series_title is the fallback grouping key for
    # episodes that haven't been scraped yet (parsed from filename).
    series_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("series.id", ondelete="SET NULL"), nullable=True, index=True
    )
    series_title: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # User data
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5, null = unrated
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    is_watched: Mapped[bool] = mapped_column(Boolean, default=False)
    # Metadata-ignore — user opted this item out of the metadata workspace.
    # Ignored media are hidden from "incomplete metadata" lists and skipped by
    # batch scrapes until un-ignored again.
    metadata_ignored: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", index=True)

    # Playback progress
    playback_position: Mapped[float] = mapped_column(Float, default=0.0)  # seconds
    playback_speed: Mapped[float | None] = mapped_column(Float, nullable=True)  # per-media memory
    last_played_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    # Soft delete (recycle bin)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("library_id", "file_path", name="uq_media_library_file"),
    )

    # File missing — local file was deleted externally but record is kept.
    # When True, media_type may be OFFLINE. Scanner/watchdog maintains this.
    file_missing: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", index=True)
    missing_detected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Poster source — distinguishes a user-uploaded cover ("custom") from a
    # scraped one ("scraped"). Scraping skips cover download when the user
    # uploaded their own cover; only after the user deletes it will scraping
    # re-download from the source. NULL = legacy/unknown.
    poster_source: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Timestamps
    file_modified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    library: Mapped["MediaLibrary"] = relationship("MediaLibrary", back_populates="media")
    series: Mapped["Series | None"] = relationship("Series", back_populates="media")
    urls: Mapped[list["MediaUrl"]] = relationship(
        "MediaUrl", back_populates="media", cascade="all, delete-orphan"
    )
    segments: Mapped[list["Segment"]] = relationship(
        "Segment", back_populates="media", cascade="all, delete-orphan",
        order_by="Segment.start_time"
    )
    video_tags: Mapped[list["VideoTag"]] = relationship(
        "VideoTag", back_populates="media", cascade="all, delete-orphan"
    )
    subtitles: Mapped[list["Subtitle"]] = relationship(
        "Subtitle", back_populates="media", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Media {self.title}>"


class MediaUrl(Base):
    __tablename__ = "media_urls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("media.id", ondelete="CASCADE"), nullable=False
    )

    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    url_role: Mapped[UrlRole] = mapped_column(
        Enum(UrlRole, values_callable=enum_values), default=UrlRole.REFERENCE, nullable=False
    )

    # URL metadata
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(100), nullable=True)  # youtube, bilibili, etc.

    # Action tracking (L1/L2/L3)
    last_visited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    played_progress: Mapped[float] = mapped_column(Float, default=0.0)  # seconds
    is_expired: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationship
    media: Mapped["Media"] = relationship("Media", back_populates="urls")

    def __repr__(self) -> str:
        return f"<MediaUrl [{self.url_role}] {self.url[:50]}>"


# Forward references
from app.models.library import MediaLibrary  # noqa: E402, F401
from app.models.series import Series  # noqa: E402, F401
from app.models.segment import Segment  # noqa: E402, F401
from app.models.subtitle import Subtitle  # noqa: E402, F401
from app.models.tag import VideoTag  # noqa: E402, F401
