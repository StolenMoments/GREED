from __future__ import annotations

from collections.abc import Generator
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.models import PriceBar
from backend.price_bars import DAILY_INTERVAL, WEEKLY_INTERVAL
from scripts.backtest.preload_price_bars import preload_price_bars


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _daily(days: int = 8) -> pd.DataFrame:
    index = pd.bdate_range("2024-01-02", periods=days)
    return pd.DataFrame(
        {
            "Open": range(100, 100 + days),
            "High": range(110, 110 + days),
            "Low": range(90, 90 + days),
            "Close": range(105, 105 + days),
            "Volume": [1000] * days,
        },
        index=index,
    )


def test_preload_price_bars_stores_daily_and_weekly_from_one_fetch(db_session) -> None:
    calls: list[tuple[str, date]] = []

    def fetcher(ticker: str, start: date) -> pd.DataFrame:
        calls.append((ticker, start))
        return _daily()

    result = preload_price_bars(
        db_session,
        universe=[("005930", "Samsung")],
        fetcher=fetcher,
        delay_seconds=0,
    )

    daily_rows = db_session.scalars(
        select(PriceBar)
        .where(PriceBar.ticker == "005930", PriceBar.interval == DAILY_INTERVAL)
        .order_by(PriceBar.bar_date)
    ).all()
    weekly_rows = db_session.scalars(
        select(PriceBar)
        .where(PriceBar.ticker == "005930", PriceBar.interval == WEEKLY_INTERVAL)
        .order_by(PriceBar.bar_date)
    ).all()

    assert calls == [("005930", date(2011, 12, 19))]
    assert result.processed == 1
    assert result.failed == []
    assert result.daily_upserted_rows == 8
    assert result.weekly_upserted_rows == 2
    assert [row.bar_date for row in daily_rows] == list(_daily().index.date)
    assert [row.bar_date for row in weekly_rows] == [date(2024, 1, 1), date(2024, 1, 8)]


def test_preload_price_bars_continues_after_failure(db_session) -> None:
    def fetcher(ticker: str, start: date) -> pd.DataFrame:
        if ticker == "005930":
            raise RuntimeError("fetch failed")
        return _daily()

    result = preload_price_bars(
        db_session,
        universe=[("005930", "Samsung"), ("000660", "SK Hynix")],
        fetcher=fetcher,
        delay_seconds=0,
    )

    assert result.processed == 1
    assert result.failed == [("005930", "Samsung", "fetch failed")]
    assert (
        db_session.get(PriceBar, ("000660", WEEKLY_INTERVAL, date(2024, 1, 1)))
        is not None
    )
