"""Task model — replaces old singleton global dict progress framework.

TaskManager uses this table to persist task state. Completed tasks are
retained for 24h, then cleaned up. Restart marks running tasks as failed.
"""
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import TaskPriority, TaskStatus, TaskType, enum_values


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    type: Mapped[TaskType] = mapped_column(Enum(TaskType, values_callable=enum_values), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, values_callable=enum_values), default=TaskStatus.PENDING, nullable=False
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority, values_callable=enum_values), default=TaskPriority.MEDIUM, nullable=False
    )

    # Display
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Progress
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Error
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Associations (nullable — not all tasks are tied to a library or media)
    library_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("media_libraries.id", ondelete="SET NULL"), nullable=True
    )
    media_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("media.id", ondelete="SET NULL"), nullable=True
    )

    # Result (JSON for flexible result data — stored as string, parsed by workers)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Task [{self.type}] {self.title} ({self.status})>"
