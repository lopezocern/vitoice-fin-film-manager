"""Schemas for Segment."""
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMBaseModel


class SegmentCreate(BaseModel):
    """Schema for creating a segment."""
    name: str = Field(..., max_length=200)
    start_time: float = Field(..., ge=0, description="Start time in seconds")
    end_time: float | None = Field(None, ge=0, description="End time in seconds (null = point marker)")
    description: str | None = None
    color: str | None = Field(None, max_length=7)
    sort_order: int = 0


class SegmentUpdate(BaseModel):
    """Schema for updating a segment — all fields optional."""
    name: str | None = Field(None, max_length=200)
    start_time: float | None = Field(None, ge=0)
    end_time: float | None = Field(None, ge=0)
    description: str | None = None
    color: str | None = Field(None, max_length=7)
    sort_order: int | None = None


class SegmentResponse(ORMBaseModel):
    """Segment response schema."""
    id: int
    media_id: int
    name: str
    start_time: float
    end_time: float | None = None
    description: str | None = None
    color: str | None = None
    sort_order: int
    created_at: datetime
    updated_at: datetime
