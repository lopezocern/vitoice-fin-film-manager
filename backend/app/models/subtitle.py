"""Subtitle model — supports external, embedded, and network subtitles.

Phase 3.0 supports SRT/VTT/ASS/SSA formats. Network subtitles for L2 in-app
playback require manual user trigger (not automatic download during ytdlp
extraction). Subtitle style settings are global (in Setting table), not
per-media memory.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import SubtitleSourceType, enum_values


class Subtitle(Base):
    __tablename__ = "subtitles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("media.id", ondelete="CASCADE"), nullable=False
    )

    source_type: Mapped[SubtitleSourceType] = mapped_column(
        Enum(SubtitleSourceType, values_callable=enum_values), default=SubtitleSourceType.EXTERNAL, nullable=False
    )

    language: Mapped[str] = mapped_column(String(10), nullable=False)  # e.g. "zh-CN", "en"
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # File info (for external/network)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    file_format: Mapped[str | None] = mapped_column(String(10), nullable=True)  # srt, vtt, ass, ssa

    # For embedded
    stream_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # State
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_downloaded: Mapped[bool] = mapped_column(Boolean, default=False)  # for network subtitles

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationship
    media: Mapped["Media"] = relationship("Media", back_populates="subtitles")

    def __repr__(self) -> str:
        return f"<Subtitle [{self.language}] {self.title or 'untitled'}>"


# Forward reference
from app.models.media import Media  # noqa: E402, F401
