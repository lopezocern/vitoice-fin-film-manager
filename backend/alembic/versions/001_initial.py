"""Initial schema — all tables for Phase 3.0.

Revision ID: 001
Create Date: 2026-07-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # media_libraries
    op.create_table(
        "media_libraries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("type", sa.Enum("video", "audio", "document", name="librarytype"), nullable=False, server_default="video"),
        sa.Column("root_path", sa.String(500), nullable=False),
        sa.Column("scrape_mode", sa.Enum("none", "movie", "tv", "av", "custom", name="scrapemode"), nullable=False, server_default="none"),
        sa.Column("watch_enabled", sa.Boolean, server_default=sa.text("1")),
        sa.Column("auto_import", sa.Boolean, server_default=sa.text("1")),
        sa.Column("auto_mark_missing", sa.Boolean, server_default=sa.text("1")),
        sa.Column("auto_update_path", sa.Boolean, server_default=sa.text("0")),
        sa.Column("description", sa.Text),
        sa.Column("color", sa.String(7)),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # media
    op.create_table(
        "media",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("library_id", sa.Integer, sa.ForeignKey("media_libraries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("file_path", sa.String(1000)),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("media_type", sa.Enum("local", "network", "both", name="mediatype"), nullable=False, server_default="local"),
        sa.Column("file_size", sa.Integer),
        sa.Column("file_hash", sa.String(64)),
        sa.Column("mime_type", sa.String(100)),
        sa.Column("duration", sa.Float),
        sa.Column("width", sa.Integer),
        sa.Column("height", sa.Integer),
        sa.Column("codec", sa.String(50)),
        sa.Column("fps", sa.Float),
        sa.Column("bitrate", sa.Integer),
        sa.Column("thumbnail_path", sa.String(1000)),
        sa.Column("poster_path", sa.String(1000)),
        sa.Column("description", sa.Text),
        sa.Column("rating", sa.Integer),
        sa.Column("is_favorite", sa.Boolean, server_default=sa.text("0")),
        sa.Column("is_watched", sa.Boolean, server_default=sa.text("0")),
        sa.Column("playback_position", sa.Float, server_default="0.0"),
        sa.Column("playback_speed", sa.Float),
        sa.Column("file_modified_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_media_library_id", "media", ["library_id"])
    op.create_index("ix_media_title", "media", ["title"])

    # media_urls
    op.create_table(
        "media_urls",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("media_id", sa.Integer, sa.ForeignKey("media.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(2000), nullable=False),
        sa.Column("url_role", sa.Enum("source", "reference", name="urlrole"), nullable=False, server_default="reference"),
        sa.Column("title", sa.String(500)),
        sa.Column("platform", sa.String(100)),
        sa.Column("last_visited_at", sa.DateTime),
        sa.Column("played_progress", sa.Float, server_default="0.0"),
        sa.Column("is_expired", sa.Boolean, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_media_urls_media_id", "media_urls", ["media_id"])

    # tag_types
    op.create_table(
        "tag_types",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
        sa.Column("color", sa.String(7), server_default="#635bff"),
        sa.Column("is_builtin", sa.Boolean, server_default=sa.text("0")),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # tags
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("tag_type_id", sa.Integer, sa.ForeignKey("tag_types.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("tags.id", ondelete="SET NULL")),
        sa.Column("description", sa.Text),
        sa.Column("color", sa.String(7)),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_tags_tag_type_id", "tags", ["tag_type_id"])

    # video_tags
    op.create_table(
        "video_tags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("media_id", sa.Integer, sa.ForeignKey("media.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag_id", sa.Integer, sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(20), server_default="manual"),
        sa.Column("confidence", sa.Float),
        sa.Column("is_verified", sa.Boolean, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_video_tags_media_id", "video_tags", ["media_id"])
    op.create_index("ix_video_tags_tag_id", "video_tags", ["tag_id"])
    op.create_unique_constraint("uq_video_tags_media_tag", "video_tags", ["media_id", "tag_id"])

    # segments
    op.create_table(
        "segments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("media_id", sa.Integer, sa.ForeignKey("media.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("start_time", sa.Float, nullable=False),
        sa.Column("end_time", sa.Float),
        sa.Column("description", sa.Text),
        sa.Column("color", sa.String(7)),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_segments_media_id", "segments", ["media_id"])

    # subtitles
    op.create_table(
        "subtitles",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("media_id", sa.Integer, sa.ForeignKey("media.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.Enum("external", "embedded", "network", name="subtitlesourcetype"), nullable=False, server_default="external"),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("file_path", sa.String(1000)),
        sa.Column("file_format", sa.String(10)),
        sa.Column("stream_index", sa.Integer),
        sa.Column("is_default", sa.Boolean, server_default=sa.text("0")),
        sa.Column("is_downloaded", sa.Boolean, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # smart_folders
    op.create_table(
        "smart_folders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("rule_json", sa.JSON, nullable=False),
        sa.Column("preview_count", sa.Integer, server_default="0"),
        sa.Column("color", sa.String(7)),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # tasks
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("type", sa.Enum("scan", "thumbnail", "metadata", "ai_tag", "subtitle", "hash", "scrape", name="tasktype"), nullable=False),
        sa.Column("status", sa.Enum("pending", "running", "completed", "failed", "cancelled", name="taskstatus"), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Enum("high", "medium", "low", name="taskpriority"), nullable=False, server_default="medium"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("subtitle", sa.String(200)),
        sa.Column("progress", sa.Integer, server_default="0"),
        sa.Column("total", sa.Integer),
        sa.Column("current", sa.Integer),
        sa.Column("error_msg", sa.Text),
        sa.Column("library_id", sa.Integer, sa.ForeignKey("media_libraries.id", ondelete="SET NULL")),
        sa.Column("media_id", sa.Integer, sa.ForeignKey("media.id", ondelete="SET NULL")),
        sa.Column("result", sa.Text),
        sa.Column("started_at", sa.DateTime),
        sa.Column("completed_at", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # settings
    op.create_table(
        "settings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(100), unique=True, nullable=False),
        sa.Column("value", sa.Text),
        sa.Column("type", sa.Enum("string", "int", "float", "bool", "json", "path", name="settingtype"), nullable=False, server_default="string"),
        sa.Column("category", sa.String(50), server_default="general"),
        sa.Column("description", sa.String(500)),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # Insert default tag types
    op.execute("""
        INSERT INTO tag_types (name, color, is_builtin, sort_order) VALUES
        ('actor', '#635bff', 1, 0),
        ('genre', '#f59e0b', 1, 1),
        ('theme', '#34c759', 1, 2),
        ('custom', '#8e8e93', 1, 3),
        ('collection', '#27D2BF', 1, 4)
    """)

    # Insert default settings
    op.execute("""
        INSERT INTO settings (key, value, type, category, description) VALUES
        ('theme', 'system', 'string', 'appearance', 'UI theme: light/dark/system'),
        ('language', 'zh-CN', 'string', 'appearance', 'UI language'),
        ('thumbnail_size', '320', 'int', 'thumbnail', 'Thumbnail width in pixels'),
        ('thumbnail_quality', '85', 'int', 'thumbnail', 'Thumbnail JPEG quality'),
        ('thumbnail_time_offset', '10.0', 'float', 'thumbnail', 'Thumbnail capture time offset (seconds)'),
        ('ffmpeg_path', 'ffmpeg', 'path', 'tools', 'ffmpeg binary path'),
        ('ffprobe_path', 'ffprobe', 'path', 'tools', 'ffprobe binary path'),
        ('ytdlp_path', 'yt-dlp', 'path', 'tools', 'yt-dlp binary path'),
        ('ai_api_base', 'https://api.openai.com/v1', 'string', 'ai', 'AI API base URL'),
        ('ai_api_key', '', 'string', 'ai', 'AI API key'),
        ('ai_model', 'gpt-4o-mini', 'string', 'ai', 'AI model name'),
        ('ai_trigger_on_import', '0', 'bool', 'ai', 'Auto-trigger AI tagging on import'),
        ('step_size', '5', 'float', 'player', 'Arrow key step size (seconds)'),
        ('step_unit', 'seconds', 'string', 'player', 'Step unit: seconds/frames'),
        ('subtitle_font_size', '16', 'int', 'subtitle', 'Subtitle font size'),
        ('subtitle_color', '#FFFFFF', 'string', 'subtitle', 'Subtitle text color'),
        ('subtitle_stroke', '2', 'int', 'subtitle', 'Subtitle stroke width'),
        ('subtitle_bg_opacity', '0.5', 'float', 'subtitle', 'Subtitle background opacity'),
        ('subtitle_position', 'bottom', 'string', 'subtitle', 'Subtitle position')
    """)


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_table("tasks")
    op.drop_table("smart_folders")
    op.drop_table("subtitles")
    op.drop_table("segments")
    op.drop_table("video_tags")
    op.drop_table("tags")
    op.drop_table("tag_types")
    op.drop_table("media_urls")
    op.drop_table("media")
    op.drop_table("media_libraries")
