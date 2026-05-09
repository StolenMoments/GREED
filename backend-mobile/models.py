from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def _seoul_now() -> datetime:
    from datetime import timezone, timedelta
    return datetime.now(tz=timezone(timedelta(hours=9)))


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (
        Index("ix_analyses_run_id", "run_id"),
        Index("ix_analyses_ticker", "ticker"),
        Index("ix_analyses_judgment", "judgment"),
        Index("ix_analyses_name_initials", "name_initials"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_initials: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    judgment: Mapped[str] = mapped_column(String(20), nullable=False)
    trend: Mapped[str] = mapped_column(String(20), nullable=False)
    cloud_position: Mapped[str] = mapped_column(String(20), nullable=False)
    ma_alignment: Mapped[str] = mapped_column(String(20), nullable=False)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_price_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_price_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_seoul_now,
        nullable=False,
    )
