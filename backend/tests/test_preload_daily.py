from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from collections.abc import Generator
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.models import PriceBar
from backend.price_bars import DAILY_INTERVAL
from scripts.backtest.preload_daily import preload_daily_bars


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


def test_preload_daily_bars_resumes_from_cached_tail(db_session) -> None:
    first = pd.DataFrame(
        {"Open": [100], "High": [110], "Low": [90], "Close": [105], "Volume": [1000]},
        index=pd.to_datetime(["2024-01-02"]),
    )
    second = pd.DataFrame(
        {"Open": [101], "High": [111], "Low": [91], "Close": [106], "Volume": [1000]},
        index=pd.to_datetime(["2024-01-03"]),
    )
    calls = [first, second]
    starts: list[date] = []

    def fetcher(ticker: str, start: date) -> pd.DataFrame:
        assert ticker == "005930"
        starts.append(start)
        return calls.pop(0)

    preload_daily_bars(db_session, universe=[("005930", "Samsung")], fetcher=fetcher)
    preload_daily_bars(db_session, universe=[("005930", "Samsung")], fetcher=fetcher)

    rows = db_session.scalars(
        select(PriceBar).where(
            PriceBar.ticker == "005930",
            PriceBar.interval == DAILY_INTERVAL,
        )
    ).all()
    assert starts == [date(2011, 12, 19), date(2024, 1, 3)]
    assert len(rows) == 2
    assert rows[-1].close == 106


def test_preload_daily_bars_continues_after_fetch_failure(db_session) -> None:
    def fetcher(ticker: str, start: date) -> pd.DataFrame:
        if ticker == "005930":
            raise RuntimeError("fetch failed")
        return pd.DataFrame(
            {"Open": [100], "High": [110], "Low": [90], "Close": [105], "Volume": [1000]},
            index=pd.to_datetime(["2024-01-02"]),
        )

    result = preload_daily_bars(
        db_session,
        universe=[("005930", "Samsung"), ("000660", "SK Hynix")],
        fetcher=fetcher,
    )

    assert result.processed == 1
    assert result.failed == [("005930", "Samsung", "fetch failed")]
    assert db_session.get(PriceBar, ("000660", DAILY_INTERVAL, date(2024, 1, 2))) is not None


def test_preload_daily_bars_skips_empty_response_when_cache_exists(db_session) -> None:
    seeded = pd.DataFrame(
        {"Open": [100], "High": [110], "Low": [90], "Close": [105], "Volume": [1000]},
        index=pd.to_datetime(["2024-01-02"]),
    )
    starts: list[date] = []

    def seed_fetcher(ticker: str, start: date) -> pd.DataFrame:
        return seeded

    def empty_fetcher(ticker: str, start: date) -> pd.DataFrame:
        starts.append(start)
        return pd.DataFrame()

    preload_daily_bars(db_session, universe=[("005930", "Samsung")], fetcher=seed_fetcher)
    result = preload_daily_bars(db_session, universe=[("005930", "Samsung")], fetcher=empty_fetcher)

    assert starts == [date(2024, 1, 3)]
    assert result.processed == 0
    assert result.skipped == 1
    assert result.failed == []


def test_preload_daily_bars_fails_empty_response_when_cache_missing(db_session) -> None:
    def fetcher(ticker: str, start: date) -> pd.DataFrame:
        return pd.DataFrame()

    result = preload_daily_bars(db_session, universe=[("005930", "Samsung")], fetcher=fetcher)

    assert result.processed == 0
    assert result.skipped == 0
    assert result.failed == [("005930", "Samsung", "no daily data returned")]


def test_preload_daily_bars_sleeps_between_successful_requests(db_session) -> None:
    sleeps: list[float] = []

    def fetcher(ticker: str, start: date) -> pd.DataFrame:
        return pd.DataFrame(
            {"Open": [100], "High": [110], "Low": [90], "Close": [105], "Volume": [1000]},
            index=pd.to_datetime(["2024-01-02"]),
        )

    preload_daily_bars(
        db_session,
        universe=[("005930", "Samsung"), ("000660", "SK Hynix")],
        fetcher=fetcher,
        delay_seconds=1.25,
        sleeper=sleeps.append,
    )

    assert sleeps == [1.25]


def test_preload_daily_bars_retries_with_backoff_before_marking_failure(db_session) -> None:
    attempts = 0
    sleeps: list[float] = []

    def fetcher(ticker: str, start: date) -> pd.DataFrame:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("temporary throttled")
        return pd.DataFrame(
            {"Open": [100], "High": [110], "Low": [90], "Close": [105], "Volume": [1000]},
            index=pd.to_datetime(["2024-01-02"]),
        )

    result = preload_daily_bars(
        db_session,
        universe=[("005930", "Samsung")],
        fetcher=fetcher,
        retries=2,
        retry_backoff_seconds=2.0,
        sleeper=sleeps.append,
    )

    assert attempts == 3
    assert sleeps == [2.0, 4.0]
    assert result.processed == 1
    assert result.failed == []
