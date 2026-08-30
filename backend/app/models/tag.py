"""TagType, Tag, and VideoTag models.

TagType is an enumeration (actor, genre, theme, custom, ...) — the old system
left tag_type unenumerated, which caused inconsistency. VideoTag now includes
traceability columns (source, confidence) for AI tagging.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TagType(Base):
    """Tag category — e.g. actor, genre, theme, custom."""
    __tablename__ = "tag_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#635bff")  # hex
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationship
    tags: Mapped[list["Tag"]] = relationship(
        "Tag", back_populates="tag_type", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<TagType {self.name}>"


class Tag(Base):
    """Individual tag — belongs to a TagType, supports hierarchy."""
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    tag_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tag_types.id", ondelete="CASCADE"), nullable=False
    )

    # Hierarchy (3-level max)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tags.id", ondelete="SET NULL"), nullable=True
    )

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # override type color
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    tag_type: Mapped["TagType"] = relationship("TagType", back_populates="tags")
    parent: Mapped["Tag | None"] = relationship(
        "Tag", remote_side="Tag.id", back_populates="children"
    )
    children: Mapped[list["Tag"]] = relationship("Tag", back_populates="parent")
    video_tags: Mapped[list["VideoTag"]] = relationship(
        "VideoTag", back_populates="tag", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Tag {self.name}>"


class VideoTag(Base):
    """Association table: Media <-> Tag, with traceability for AI tagging."""
    __tablename__ = "video_tags"
    __table_args__ = (
        UniqueConstraint("media_id", "tag_id", name="uq_video_tags_media_tag"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("media.id", ondelete="CASCADE"), nullable=False
    )
    tag_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False
    )

    # Traceability (new — old system lacked these)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | ai | scrape
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0.0-1.0 for AI
    is_verified: Mapped[bool] = mapped_column(Boolean, default=True)  # false for AI pending review

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    media: Mapped["Media"] = relationship("Media", back_populates="video_tags")
    tag: Mapped["Tag"] = relationship("Tag", back_populates="video_tags")

    def __repr__(self) -> str:
        return f"<VideoTag media={self.media_id} tag={self.tag_id} [{self.source}]>"


# Forward references
from app.models.media import Media  # noqa: E402, F401
