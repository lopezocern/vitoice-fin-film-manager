"""Schemas for TagType, Tag, and VideoTag."""
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMBaseModel


class TagTypeCreate(BaseModel):
    """Schema for creating a tag type."""
    name: str = Field(..., max_length=50)
    color: str = Field("#635bff", max_length=7)
    is_builtin: bool = False
    sort_order: int = 0


class TagTypeUpdate(BaseModel):
    """Schema for updating a tag type — all fields optional."""
    name: str | None = Field(None, max_length=50)
    color: str | None = Field(None, max_length=7)
    sort_order: int | None = None


class TagTypeResponse(ORMBaseModel):
    """Tag type response schema."""
    id: int
    name: str
    color: str
    is_builtin: bool
    sort_order: int
    created_at: datetime


class TagCreate(BaseModel):
    """Schema for creating a tag."""
    name: str = Field(..., max_length=100)
    tag_type_id: int | None = None
    parent_id: int | None = None
    description: str | None = None
    color: str | None = Field(None, max_length=7)
    sort_order: int = 0


class TagUpdate(BaseModel):
    """Schema for updating a tag — all fields optional."""
    name: str | None = Field(None, max_length=100)
    tag_type_id: int | None = None
    parent_id: int | None = None
    description: str | None = None
    color: str | None = Field(None, max_length=7)
    sort_order: int | None = None


class TagResponse(ORMBaseModel):
    """Tag response schema — includes children for tree building."""
    id: int
    name: str
    tag_type_id: int
    parent_id: int | None = None
    description: str | None = None
    color: str | None = None
    sort_order: int
    created_at: datetime
    updated_at: datetime
    children: list["TagResponse"] = []
    media_count: int | None = None


class VideoTagCreate(BaseModel):
    """Schema for creating a media-tag association."""
    media_id: int
    tag_id: int
    source: str = Field("manual", max_length=20, description="manual | ai | scrape")
    confidence: float | None = Field(None, ge=0.0, le=1.0, description="AI confidence 0.0-1.0")
    is_verified: bool = True


class VideoTagResponse(ORMBaseModel):
    """VideoTag association response schema."""
    id: int
    media_id: int
    tag_id: int
    source: str
    confidence: float | None = None
    is_verified: bool
    created_at: datetime


# Resolve forward reference after class definition
TagResponse.model_rebuild()
