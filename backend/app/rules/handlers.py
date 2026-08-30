"""Built-in RuleHandlers — 8 dimensions for smart folder rules.

Each handler validates input and generates SQL for one filtering dimension.
New dimensions can be added by creating a handler and registering it —
no need to modify the engine (open/closed principle).
"""
from typing import Any

from sqlalchemy import select
from sqlalchemy.sql.elements import BinaryExpression

from app.models.media import Media
from app.models.tag import VideoTag
from app.rules.base import RuleHandler, registry


class TagHandler(RuleHandler):
    """Filter by tag membership. Supports: has, not_has, has_any, has_all."""
    dimension = "tag"

    def validate(self, operator: str, value: Any) -> bool:
        if operator in ("has", "not_has"):
            return isinstance(value, int)
        if operator in ("has_any", "has_all"):
            return isinstance(value, list) and all(isinstance(v, int) for v in value)
        return False

    def to_sql(self, operator: str, value: Any) -> BinaryExpression | None:
        if operator == "has":
            return Media.id.in_(
                select(VideoTag.media_id).where(VideoTag.tag_id == value)
            )
        elif operator == "not_has":
            return Media.id.notin_(
                select(VideoTag.media_id).where(VideoTag.tag_id == value)
            )
        elif operator == "has_any":
            return Media.id.in_(
                select(VideoTag.media_id).where(VideoTag.tag_id.in_(value))
            )
        elif operator == "has_all":
            # Has all tags: media_id appears N times for N tags
            return Media.id.in_(
                select(VideoTag.media_id)
                .where(VideoTag.tag_id.in_(value))
                .group_by(VideoTag.media_id)
                .having(count_distinct(VideoTag.tag_id) == len(value))
            )
        return None


class DurationHandler(RuleHandler):
    """Filter by duration in seconds. Supports: gt, lt, gte, lte, between."""
    dimension = "duration"

    def validate(self, operator: str, value: Any) -> bool:
        if operator == "between":
            return isinstance(value, list) and len(value) == 2
        return isinstance(value, (int, float))

    def to_sql(self, operator: str, value: Any) -> BinaryExpression | None:
        col = Media.duration
        ops = {
            "gt": lambda: col > value,
            "lt": lambda: col < value,
            "gte": lambda: col >= value,
            "lte": lambda: col <= value,
            "eq": lambda: col == value,
            "between": lambda: col.between(value[0], value[1]),
        }
        fn = ops.get(operator)
        return fn() if fn else None


class ResolutionHandler(RuleHandler):
    """Filter by minimum resolution height. Supports: gte, lte, eq."""
    dimension = "resolution"

    def validate(self, operator: str, value: Any) -> bool:
        if operator in ("gte", "lte", "eq"):
            return isinstance(value, int) and value in (360, 480, 720, 1080, 1440, 2160, 4320)
        return False

    def to_sql(self, operator: str, value: Any) -> BinaryExpression | None:
        col = Media.height
        ops = {
            "gte": lambda: col >= value,
            "lte": lambda: col <= value,
            "eq": lambda: col == value,
        }
        fn = ops.get(operator)
        return fn() if fn else None


class RatingHandler(RuleHandler):
    """Filter by user rating (1-5). Supports: gte, lte, eq, is_null."""
    dimension = "rating"

    def validate(self, operator: str, value: Any) -> bool:
        if operator == "is_null":
            return value is True or value is False
        return isinstance(value, int) and 1 <= value <= 5

    def to_sql(self, operator: str, value: Any) -> BinaryExpression | None:
        col = Media.rating
        if operator == "is_null":
            return col.is_(None) if value else col.is_not(None)
        ops = {
            "gte": lambda: col >= value,
            "lte": lambda: col <= value,
            "eq": lambda: col == value,
        }
        fn = ops.get(operator)
        return fn() if fn else None


class FavoriteHandler(RuleHandler):
    """Filter by favorite status. Supports: eq (True/False)."""
    dimension = "favorite"

    def validate(self, operator: str, value: Any) -> bool:
        return operator == "eq" and isinstance(value, bool)

    def to_sql(self, operator: str, value: Any) -> BinaryExpression | None:
        return Media.is_favorite == value


class LibraryHandler(RuleHandler):
    """Filter by library ID. Supports: eq, in."""
    dimension = "library"

    def validate(self, operator: str, value: Any) -> bool:
        if operator == "eq":
            return isinstance(value, int)
        if operator == "in":
            return isinstance(value, list) and all(isinstance(v, int) for v in value)
        return False

    def to_sql(self, operator: str, value: Any) -> BinaryExpression | None:
        if operator == "eq":
            return Media.library_id == value
        elif operator == "in":
            return Media.library_id.in_(value)
        return None


class MediaTypeHandler(RuleHandler):
    """Filter by media type. Supports: eq."""
    dimension = "media_type"

    def validate(self, operator: str, value: Any) -> bool:
        return operator == "eq" and value in ("local", "network", "both")

    def to_sql(self, operator: str, value: Any) -> BinaryExpression | None:
        return Media.media_type == value


class FileSizeHandler(RuleHandler):
    """Filter by file size in MB. Supports: gt, lt, gte, lte."""
    dimension = "file_size"

    def validate(self, operator: str, value: Any) -> bool:
        return isinstance(value, (int, float)) and operator in ("gt", "lt", "gte", "lte")

    def to_sql(self, operator: str, value: Any) -> BinaryExpression | None:
        col = Media.file_size
        bytes_value = value * 1024 * 1024  # MB to bytes
        ops = {
            "gt": lambda: col > bytes_value,
            "lt": lambda: col < bytes_value,
            "gte": lambda: col >= bytes_value,
            "lte": lambda: col <= bytes_value,
        }
        fn = ops.get(operator)
        return fn() if fn else None


class SeasonHandler(RuleHandler):
    """Filter by season number. Supports: eq, gte, lte, is_null."""
    dimension = "season"

    def validate(self, operator: str, value: Any) -> bool:
        if operator == "is_null":
            return value is True or value is False
        return isinstance(value, int) and value >= 1 and operator in ("eq", "gte", "lte")

    def to_sql(self, operator: str, value: Any) -> BinaryExpression | None:
        col = Media.season_number
        if operator == "is_null":
            return col.is_(None) if value else col.is_not(None)
        ops = {
            "eq": lambda: col == value,
            "gte": lambda: col >= value,
            "lte": lambda: col <= value,
        }
        fn = ops.get(operator)
        return fn() if fn else None


class EpisodeHandler(RuleHandler):
    """Filter by episode number. Supports: eq, gte, lte, is_null."""
    dimension = "episode"

    def validate(self, operator: str, value: Any) -> bool:
        if operator == "is_null":
            return value is True or value is False
        return isinstance(value, int) and value >= 1 and operator in ("eq", "gte", "lte")

    def to_sql(self, operator: str, value: Any) -> BinaryExpression | None:
        col = Media.episode_number
        if operator == "is_null":
            return col.is_(None) if value else col.is_not(None)
        ops = {
            "eq": lambda: col == value,
            "gte": lambda: col >= value,
            "lte": lambda: col <= value,
        }
        fn = ops.get(operator)
        return fn() if fn else None


# Helper for has_all tags
from sqlalchemy import func

def count_distinct(col):
    return func.count(col.distinct())


class PlaybackHandler(RuleHandler):
    """Filter by playback position (seconds, > 0 = in progress).

    Supports: gt, gte, is_null. Powers the "继续观看" preset folder.
    """
    dimension = "playback"

    def validate(self, operator: str, value: Any) -> bool:
        if operator == "is_null":
            return value is True or value is False
        return isinstance(value, (int, float)) and operator in ("gt", "gte")

    def to_sql(self, operator: str, value: Any) -> BinaryExpression | None:
        col = Media.playback_position
        if operator == "is_null":
            # "未开始" = position 0 或 NULL; "有进度" = > 0
            return col.is_(None) if value else col > 0
        ops = {
            "gt": lambda: col > value,
            "gte": lambda: col >= value,
        }
        fn = ops.get(operator)
        return fn() if fn else None


class WatchedHandler(RuleHandler):
    """Filter by watched status. Supports: eq (True/False)."""
    dimension = "watched"

    def validate(self, operator: str, value: Any) -> bool:
        return operator == "eq" and isinstance(value, bool)

    def to_sql(self, operator: str, value: Any) -> BinaryExpression | None:
        return Media.is_watched == value


class MissingHandler(RuleHandler):
    """Filter by local-file-missing status. Supports: eq (True/False)."""
    dimension = "missing"

    def validate(self, operator: str, value: Any) -> bool:
        return operator == "eq" and isinstance(value, bool)

    def to_sql(self, operator: str, value: Any) -> BinaryExpression | None:
        return Media.file_missing == value


class RecentHandler(RuleHandler):
    """Filter by created_at recency (days). Supports: gte (older than), lte (within)."""
    dimension = "recent"

    def validate(self, operator: str, value: Any) -> bool:
        return isinstance(value, (int, float)) and operator in ("gte", "lte")

    def to_sql(self, operator: str, value: Any) -> BinaryExpression | None:
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=value)
        col = Media.created_at
        ops = {
            "gte": lambda: col >= cutoff,
            "lte": lambda: col <= cutoff,
        }
        fn = ops.get(operator)
        return fn() if fn else None


class NoTagHandler(RuleHandler):
    """Filter by "has no tags at all". Supports: eq (True = untagged)."""
    dimension = "no_tag"

    def validate(self, operator: str, value: Any) -> bool:
        return operator == "eq" and isinstance(value, bool)

    def to_sql(self, operator: str, value: Any) -> BinaryExpression | None:
        tagged_ids = select(VideoTag.media_id).distinct()
        return Media.id.notin_(tagged_ids) if value else Media.id.in_(tagged_ids)


# Register all handlers
registry.register(TagHandler())
registry.register(DurationHandler())
registry.register(ResolutionHandler())
registry.register(RatingHandler())
registry.register(FavoriteHandler())
registry.register(LibraryHandler())
registry.register(MediaTypeHandler())
registry.register(FileSizeHandler())
registry.register(SeasonHandler())
registry.register(EpisodeHandler())
registry.register(PlaybackHandler())
registry.register(WatchedHandler())
registry.register(MissingHandler())
registry.register(RecentHandler())
registry.register(NoTagHandler())
