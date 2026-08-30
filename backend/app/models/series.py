"""Series model — aggregates episodes of a TV show into a single entity.

A Series groups multiple Media records (episodes) that belong to the same TV
show. Grouping uses tmdb_id as the primary key (set during scraping) with a
fallback to a normalized title (set during the aggregation task that runs
after scanning). This dual-key approach lets episodes cluster together even
before TMDB metadata is fetched, then upgrades to a more reliable tmdb_id
binding once scraping completes.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Series(Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    library_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("media_libraries.id", ondelete="CASCADE"), nullable=False
    )

    # Identity — tmdb_id is the preferred grouping key; title is the fallback
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Scraped metadata (series-level, shared across all episodes)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    poster_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    scrape_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Series stats from TMDB (cached for display without re-fetching)
    total_seasons: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_episodes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Actual episode count in this library (refreshed by aggregation task)
    episode_count: Mapped[int] = mapped_column(Integer, default=0)

    # Metadata
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    media: Mapped[list["Media"]] = relationship(
        "Media", back_populates="series"
    )

    def __repr__(self) -> str:
        return f"<Series {self.title} ({self.episode_count} eps)>"


# Forward references
from app.models.media import Media  # noqa: E402, F401
