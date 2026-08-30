"""SmartFolder model — virtual folder defined by rules, doesn't move files.

rule_json stores a serialized rule tree. preview_count is cached and refreshed
periodically (on sidebar open). The rule engine uses registered RuleHandler
architecture (see app/rules/), replacing the old if/elif hardcoding.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import JSON

from app.database import Base


class SmartFolder(Base):
    __tablename__ = "smart_folders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Serialized rule tree — see app/rules/engine.py for structure
    rule_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Cached hit count (refreshed on sidebar open, not real-time)
    preview_count: Mapped[int] = mapped_column(Integer, default=0)

    # System-preset folders (seeded idempotently on first list). They behave
    # like user folders but the frontend hides delete/edit affordances.
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<SmartFolder {self.name} ({self.preview_count} hits)>"
