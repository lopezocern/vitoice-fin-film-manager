"""Schemas for Task."""
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.enums import TaskPriority, TaskStatus, TaskType
from app.schemas.common import ORMBaseModel


class TaskCreate(BaseModel):
    """Schema for creating a task."""
    type: TaskType
    priority: TaskPriority = TaskPriority.MEDIUM
    title: str = Field(..., max_length=200)
    subtitle: str | None = Field(None, max_length=200)
    library_id: int | None = None
    media_id: int | None = None
    total: int | None = None


class TaskResponse(ORMBaseModel):
    """Task response schema.

    The Task model stores `result` as a JSON string in a Text column.
    This schema parses it into a dict for the API response.
    """
    id: int
    type: TaskType
    status: TaskStatus
    priority: TaskPriority
    title: str
    subtitle: str | None = None
    progress: int
    total: int | None = None
    current: int | None = None
    error_msg: str | None = None
    library_id: int | None = None
    media_id: int | None = None
    result: dict[str, Any] | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("result", mode="before")
    @classmethod
    def _parse_result_json(cls, v: Any) -> dict[str, Any] | None:
        """Parse the JSON string stored in the Text column into a dict."""
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, dict) else None
            except (json.JSONDecodeError, TypeError):
                return None
        return None
