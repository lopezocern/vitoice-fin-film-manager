"""Schemas for SmartFolder."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMBaseModel


class SmartFolderCreate(BaseModel):
    """Schema for creating a smart folder."""
    name: str = Field(..., max_length=100)
    rule_json: dict[str, Any] = Field(..., description="Serialized rule tree")
    color: str | None = Field(None, max_length=7)
    sort_order: int = 0


class SmartFolderUpdate(BaseModel):
    """Schema for updating a smart folder — all fields optional."""
    name: str | None = Field(None, max_length=100)
    rule_json: dict[str, Any] | None = None
    color: str | None = Field(None, max_length=7)
    sort_order: int | None = None


class SmartFolderResponse(ORMBaseModel):
    """Smart folder response schema."""
    id: int
    name: str
    rule_json: dict[str, Any]
    preview_count: int
    color: str | None = None
    sort_order: int
    is_system: bool = False
    created_at: datetime
    updated_at: datetime
