"""Schemas for Subtitle."""
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import SubtitleSourceType
from app.schemas.common import ORMBaseModel


class SubtitleCreate(BaseModel):
    """Schema for creating a subtitle."""
    source_type: SubtitleSourceType = SubtitleSourceType.EXTERNAL
    language: str = Field(..., max_length=10, description="Language code e.g. zh-CN, en")
    title: str | None = Field(None, max_length=200)
    file_path: str | None = Field(None, max_length=1000)
    file_format: str | None = Field(None, max_length=10, description="srt, vtt, ass, ssa")
    stream_index: int | None = Field(None, description="For embedded subtitles")
    is_default: bool = False
    is_downloaded: bool = False


class SubtitleUpdate(BaseModel):
    """Schema for updating a subtitle — all fields optional."""
    source_type: SubtitleSourceType | None = None
    language: str | None = Field(None, max_length=10)
    title: str | None = Field(None, max_length=200)
    file_path: str | None = Field(None, max_length=1000)
    file_format: str | None = Field(None, max_length=10)
    stream_index: int | None = None
    is_default: bool | None = None
    is_downloaded: bool | None = None


class SubtitleResponse(ORMBaseModel):
    """Subtitle response schema."""
    id: int
    media_id: int
    source_type: SubtitleSourceType
    language: str
    title: str | None = None
    file_path: str | None = None
    file_format: str | None = None
    stream_index: int | None = None
    is_default: bool
    is_downloaded: bool
    created_at: datetime
