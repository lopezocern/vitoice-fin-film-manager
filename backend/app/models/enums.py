"""Enum definitions shared across models."""
import enum


class MediaType(str, enum.Enum):
    """Media source type."""
    LOCAL = "local"      # 本地文件
    NETWORK = "network"  # 网络资源
    BOTH = "both"        # 本地+网络
    OFFLINE = "offline"  # 本地文件丢失，保留记录（可能有网络源可回退）


class UrlRole(str, enum.Enum):
    """URL role in MediaUrl table.

    - source: playable/downloadable URL (local type media cannot have source URL
              other than the local file to keep local file as sole playback source)
    - reference: link-only URL for source tracing (all media types can have)
    """
    SOURCE = "source"
    REFERENCE = "reference"


class ScrapeMode(str, enum.Enum):
    """Scraping configuration attached to MediaLibrary nodes."""
    NONE = "none"
    MOVIE = "movie"
    TV = "tv"
    AV = "av"
    CUSTOM = "custom"


class LibraryType(str, enum.Enum):
    """Library media type."""
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"


class TaskType(str, enum.Enum):
    SCAN = "scan"
    THUMBNAIL = "thumbnail"
    METADATA = "metadata"
    AI_TAG = "ai_tag"
    SUBTITLE = "subtitle"
    HASH = "hash"
    SCRAPE = "scrape"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SubtitleSourceType(str, enum.Enum):
    EXTERNAL = "external"
    EMBEDDED = "embedded"
    NETWORK = "network"


class SettingType(str, enum.Enum):
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    JSON = "json"
    PATH = "path"


def enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """values_callable for SQLAlchemy Enum — persist .value (lowercase) instead of .name.

    All vitoice enums inherit (str, enum.Enum) with lowercase values, so the
    database stores 'string', 'pending', 'local', etc. Without this callable,
    SQLAlchemy defaults to storing .name ('STRING', 'PENDING', 'LOCAL').
    """
    return [e.value for e in enum_cls]
