"""Segment model — time-point markers on a media's timeline.

Segment marking is a time-point dependent operation, so it belongs on the
media page (not management page). I/O shortcuts mark in/out points in the
fullscreen player.
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("media.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)  # seconds
    end_time: Mapped[float | None] = mapped_column(Float, nullable=True)  # null = point marker

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # hex

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationship
    media: Mapped["Media"] = relationship("Media", back_populates="segments")

    def __repr__(self) -> str:
        return f"<Segment {self.name} [{self.start_time}-{self.end_time}]>"


# Forward reference
from app.models.media import Media  # noqa: E402, F401
