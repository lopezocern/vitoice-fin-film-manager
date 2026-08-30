"""Model registry — import all models so they register on Base.metadata.

Importing this module ensures all tables are created by init_db() / Alembic.
"""
from app.models.library import MediaLibrary
from app.models.media import Media, MediaUrl
from app.models.series import Series
from app.models.segment import Segment
from app.models.setting import Setting
from app.models.smart_folder import SmartFolder
from app.models.subtitle import Subtitle
from app.models.tag import Tag, TagType, VideoTag
from app.models.task import Task

# Collect for easy iteration
all_models = [
    MediaLibrary,
    Media,
    MediaUrl,
    Series,
    TagType,
    Tag,
    VideoTag,
    Segment,
    Subtitle,
    SmartFolder,
    Task,
    Setting,
]

__all__ = [m.__name__ for m in all_models]
