"""Library size snapshots — the data behind the capacity trend line.

Why a table instead of computing on the fly: total size / media count are
point-in-time facts. Without recording them, "which library grew 200GB last
week" is unanswerable — the current numbers always overwrite themselves.

One row per library per day (`captured_on` is a date): repeated scans on the
same day update the row instead of piling up.
"""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, BigInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LibrarySizeSnapshot(Base):
    __tablename__ = "library_size_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    library_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("media_libraries.id", ondelete="CASCADE"), nullable=False
    )
    captured_on: Mapped[date] = mapped_column(Date, nullable=False)
    media_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    missing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    __table_args__ = (
        Index("ix_lib_size_snapshot_lib_day", "library_id", "captured_on", unique=True),
    )
