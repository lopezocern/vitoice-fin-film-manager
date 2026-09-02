"""MediaLibrary model — a managed directory with scraping config.

Scraping configuration (none/movie/tv/av/custom) is attached here, not in a
global setting. Scan settings are unified in the Setting table (no library-
level override). Library nesting is NOT allowed.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import LibraryType, ScrapeMode, enum_values


class MediaLibrary(Base):
    __tablename__ = "media_libraries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[LibraryType] = mapped_column(
        Enum(LibraryType, values_callable=enum_values), default=LibraryType.VIDEO, nullable=False
    )
    # Unique: registering the same directory twice would scan it into
    # duplicate media rows. Enforced here and in migration 020.
    root_path: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    scrape_mode: Mapped[ScrapeMode] = mapped_column(
        Enum(ScrapeMode, values_callable=enum_values), default=ScrapeMode.NONE, nullable=False
    )

    # File monitoring
    watch_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_import: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_mark_missing: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_update_path: Mapped[bool] = mapped_column(Boolean, default=False)

    # Metadata
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # hex color
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Content restriction: when True, media in this library is hidden
    # unless the user has enabled "show restricted content" in settings.
    # AV libraries default to True, but can be manually toggled per-library.
    is_restricted: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    media: Mapped[list["Media"]] = relationship(
        "Media", back_populates="library", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<MediaLibrary {self.name} ({self.root_path})>"


# Forward reference for type hints
from app.models.media import Media  # noqa: E402, F401
