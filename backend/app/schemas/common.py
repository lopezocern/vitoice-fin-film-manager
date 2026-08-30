"""Common shared schemas — pagination, standard responses, and ORM base model.

ORMBaseModel safely converts SQLAlchemy ORM objects to dicts via __dict__,
avoiding lazy-loading errors in async sessions. Unloaded relationships fall
back to their schema defaults (typically empty lists).
"""
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

T = TypeVar("T")


class ORMBaseModel(BaseModel):
    """Base model for all response schemas that derive from ORM objects.

    Uses from_attributes=True so model_validate(orm_obj) works, and adds a
    before-validator that converts ORM objects to plain dicts using vars().
    This prevents async SQLAlchemy from trying to lazy-load unloaded
    relationships (which would raise MissingGreenlet).
    """

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def _safe_orm_dict(cls, data: Any) -> Any:
        """Convert ORM objects to dicts, filtering SQLAlchemy internal state."""
        if isinstance(data, dict | BaseModel):
            return data
        try:
            return {k: v for k, v in vars(data).items() if not k.startswith("_")}
        except TypeError:
            return data


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""
    items: list[T]
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


class SuccessResponse(BaseModel):
    """Standard success response."""
    success: bool = True
    message: str = "OK"


class ErrorResponse(BaseModel):
    """Standard error response."""
    success: bool = False
    error: str
    detail: str | None = None
    code: str | None = None
