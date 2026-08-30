"""Pydantic schemas for Library endpoints."""
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from app.models.enums import LibraryType, ScrapeMode
from app.services.scanner import validate_root_path


class LibraryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    root_path: str = Field(..., min_length=1, max_length=500)
    type: LibraryType = LibraryType.VIDEO
    scrape_mode: ScrapeMode = ScrapeMode.NONE
    is_restricted: bool = False
    watch_enabled: bool = True
    auto_import: bool = True
    auto_mark_missing: bool = True
    description: str | None = None
    color: str | None = Field(None, max_length=7)
    sort_order: int = 0


class LibraryCreate(LibraryBase):
    @field_validator('root_path')
    @classmethod
    def validate_root_path_field(cls, v: str) -> str:
        """Validate root_path: must be absolute, exist, be a directory, no traversal."""
        try:
            resolved = validate_root_path(v)
            return str(resolved)
        except ValueError as e:
            raise ValueError(str(e))


class LibraryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    root_path: str | None = Field(None, min_length=1, max_length=500)
    type: LibraryType | None = None
    scrape_mode: ScrapeMode | None = None
    is_restricted: bool | None = None
    watch_enabled: bool | None = None
    auto_import: bool | None = None
    auto_mark_missing: bool | None = None
    description: str | None = None
    color: str | None = Field(None, max_length=7)
    sort_order: int | None = None

    @field_validator('root_path')
    @classmethod
    def validate_root_path_field(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            resolved = validate_root_path(v)
            return str(resolved)
        except ValueError as e:
            raise ValueError(str(e))


class LibraryResponse(BaseModel):
    """Response schema — root_path is masked to last directory name for security."""
    id: int
    name: str
    root_path: str  # Masked in API layer to show only last dir
    type: LibraryType = LibraryType.VIDEO
    scrape_mode: ScrapeMode = ScrapeMode.NONE
    is_restricted: bool = False
    color: str | None = None
    description: str | None = None
    watch_enabled: bool = True
    auto_import: bool = True
    auto_mark_missing: bool = True
    auto_metadata: bool = True
    auto_thumbnail: bool = True
    sort_order: int = 0
    created_at: str = ""
    updated_at: str = ""
    media_count: int = 0

    model_config = {"from_attributes": True}


def mask_path(path_str: str) -> str:
    """Mask a full path to show only the last directory name.

    Example: 'C:\\Users\\admin\\Videos' -> 'Videos'
             'F:\\Movie 哈利波特' -> '哈利波特'
    """
    if not path_str:
        return ""
    return Path(path_str).name or path_str
