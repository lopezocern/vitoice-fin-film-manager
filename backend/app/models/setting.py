"""Setting model — key-value pair table for flexible configuration.

The old system scattered settings across multiple tables and hardcoded fields.
This unified key-value table (with type annotation) allows easy extension
without schema migrations for new settings.
"""
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import SettingType, enum_values


class Setting(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    type: Mapped[SettingType] = mapped_column(
        Enum(SettingType, values_callable=enum_values), default=SettingType.STRING, nullable=False
    )
    category: Mapped[str] = mapped_column(String(50), default="general")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Setting {self.key}={self.value} [{self.type}]>"
