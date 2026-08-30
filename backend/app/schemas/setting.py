"""Schemas for Setting."""
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import SettingType
from app.schemas.common import ORMBaseModel


class SettingResponse(ORMBaseModel):
    """Setting response schema."""
    id: int
    key: str
    value: str | None = None
    type: SettingType
    category: str
    description: str | None = None
    updated_at: datetime


class SettingUpdate(BaseModel):
    """Schema for updating a single setting — all fields optional."""
    value: str | None = None
    type: SettingType | None = None
    category: str | None = Field(None, max_length=50)
    description: str | None = Field(None, max_length=500)


class SettingItem(BaseModel):
    """A single key-value pair for bulk updates."""
    key: str
    value: str | None = None


class SettingBulkUpdate(BaseModel):
    """Schema for bulk-updating settings."""
    settings: list[SettingItem]
