"""Pydantic schemas for request/response validation.

Exports all schema classes used by the API layer.
"""
from app.schemas.common import (
    ErrorResponse,
    ORMBaseModel,
    PaginatedResponse,
    SuccessResponse,
)
from app.schemas.library import LibraryCreate, LibraryResponse, LibraryUpdate
from app.schemas.media import (
    MediaCreate,
    MediaFilter,
    MediaListResponse,
    MediaResponse,
    MediaUpdate,
    MediaUrlCreate,
    MediaUrlResponse,
    PlaybackProgressUpdate,
)
from app.schemas.segment import SegmentCreate, SegmentResponse, SegmentUpdate
from app.schemas.setting import (
    SettingBulkUpdate,
    SettingItem,
    SettingResponse,
    SettingUpdate,
)
from app.schemas.smart_folder import (
    SmartFolderCreate,
    SmartFolderResponse,
    SmartFolderUpdate,
)
from app.schemas.subtitle import SubtitleCreate, SubtitleResponse, SubtitleUpdate
from app.schemas.tag import (
    TagCreate,
    TagResponse,
    TagTypeCreate,
    TagTypeResponse,
    TagUpdate,
    VideoTagCreate,
    VideoTagResponse,
)
from app.schemas.task import TaskCreate, TaskResponse

__all__ = [
    # common
    "ORMBaseModel",
    "PaginatedResponse",
    "SuccessResponse",
    "ErrorResponse",
    # library
    "LibraryCreate",
    "LibraryUpdate",
    "LibraryResponse",
    # media
    "MediaCreate",
    "MediaUpdate",
    "MediaResponse",
    "MediaListResponse",
    "MediaFilter",
    "MediaUrlCreate",
    "MediaUrlResponse",
    "PlaybackProgressUpdate",
    # tag
    "TagTypeCreate",
    "TagTypeResponse",
    "TagCreate",
    "TagUpdate",
    "TagResponse",
    "VideoTagCreate",
    "VideoTagResponse",
    # segment
    "SegmentCreate",
    "SegmentUpdate",
    "SegmentResponse",
    # subtitle
    "SubtitleCreate",
    "SubtitleUpdate",
    "SubtitleResponse",
    # smart_folder
    "SmartFolderCreate",
    "SmartFolderUpdate",
    "SmartFolderResponse",
    # task
    "TaskResponse",
    "TaskCreate",
    # setting
    "SettingResponse",
    "SettingUpdate",
    "SettingBulkUpdate",
    "SettingItem",
]
