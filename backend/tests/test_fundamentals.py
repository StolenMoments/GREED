from __future__ import annotations

from collections.abc import Generator
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend import crud, fundamentals
from backend.database import Base
from backend.fundamentals import (
    _clean,
    fetch_and_store_fundamental,
    fetch_and_store_history,
    get_or_fetch_fundamental,
    get_or_fetch_history,
    valuation_band,
)
from backend.timezone import seoul_now


@pytest.fixture()
def db() -> Generator[Session, None, None]:
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


SNAPSHOT = {
    "snapshot_date": date(2026, 5, 29),
    "per": 12.3,
    "pbr": 0.9,
    "eps": 8200.0,
    "bps": 110000.0,
    "div_yield": 2.5,
    "market_cap": 450_000_000_000.0,
}


def _fake_fetcher(_ticker: str) -> dict:
    return dict(SNAPSHOT)


def test_clean_maps_invalid_values_to_none() -> None:
    assert _clean(float("nan")) is None
    assert _clean(float("inf")) is None
    assert _clean(None) is None
    assert _clean("not a number") is None
    assert _clean("12.5") == 12.5
    assert _clean(0) == 0.0


def test_fetch_and_store_persists_snapshot(db: Session) -> None:
    row = fetch_and_store_fundamental(db, "5930", fetcher=_fake_fetcher)

    assert row is not None
    assert row.ticker == "005930"  # normalized to 6 digits
    assert row.per == 12.3
    assert row.market_cap == 450_000_000_000.0

    stored = crud.get_fundamental_snapshot(db, "005930")
    assert stored is not None
    assert stored.pbr == 0.9


def test_fetch_and_store_returns_none_when_fetcher_returns_none(db: Session) -> None:
    row = fetch_and_store_fundamental(db, "005930", fetcher=lambda _t: None)

    assert row is None
    assert crud.get_fundamental_snapshot(db, "005930") is None


def test_get_or_fetch_reuses_todays_cache(db: Session) -> None:
    calls: list[str] = []

    def counting_fetcher(ticker: str) -> dict:
        calls.append(ticker)
        return dict(SNAPSHOT)

    first = get_or_fetch_fundamental(db, "005930", fetcher=counting_fetcher)
    second = get_or_fetch_fundamental(db, "005930", fetcher=counting_fetcher)

    assert first is not None and second is not None
    assert len(calls) == 1  # second call served from today's cache


def test_get_or_fetch_refetches_when_cache_is_stale(db: Session) -> None:
    fetch_and_store_fundamental(db, "005930", fetcher=_fake_fetcher)
    stale = crud.get_fundamental_snapshot(db, "005930")
    assert stale is not None
    stale.fetched_at = seoul_now() - timedelta(days=2)
    db.commit()

    calls: list[str] = []

    def counting_fetcher(ticker: str) -> dict:
        calls.append(ticker)
        return dict(SNAPSHOT)

    get_or_fetch_fundamental(db, "005930", fetcher=counting_fetcher)

    assert len(calls) == 1  # stale cache triggered a refetch


def test_get_or_fetch_falls_back_to_stale_when_refetch_yields_none(db: Session) -> None:
    fetch_and_store_fundamental(db, "005930", fetcher=_fake_fetcher)
    stale = crud.get_fundamental_snapshot(db, "005930")
    assert stale is not None
    stale.fetched_at = seoul_now() - timedelta(days=2)
    db.commit()

    result = get_or_fetch_fundamental(db, "005930", fetcher=lambda _t: None)

    assert result is not None  # returns the stale cached snapshot
    assert result.per == 12.3


def _fake_history(_ticker: str) -> list[dict]:
    return [
        {"snapshot_date": date(2025, 3, 31), "per": 8.0, "pbr": 0.6, "eps": 7000.0, "bps": 100000.0, "div_yield": 3.0},
        {"snapshot_date": date(2025, 6, 30), "per": 10.0, "pbr": 0.7, "eps": 7500.0, "bps": 104000.0, "div_yield": 2.8},
        {"snapshot_date": date(2025, 9, 30), "per": 14.0, "pbr": 0.85, "eps": 7900.0, "bps": 107000.0, "div_yield": 2.6},
        {"snapshot_date": date(2025, 12, 31), "per": 25.0, "pbr": 1.1, "eps": 8100.0, "bps": 109000.0, "div_yield": 2.5},
    ]


def test_fetch_and_store_history_persists_rows(db: Session) -> None:
    count = fetch_and_store_history(db, "5930", fetcher=_fake_history)

    assert count == 4
    stored = crud.get_fundamental_history(db, "005930")
    assert [r.snapshot_date for r in stored] == [
        date(2025, 3, 31),
        date(2025, 6, 30),
        date(2025, 9, 30),
        date(2025, 12, 31),
    ]
    assert stored[0].per == 8.0


def test_get_or_fetch_history_reuses_todays_cache(db: Session) -> None:
    calls: list[str] = []

    def counting(ticker: str) -> list[dict]:
        calls.append(ticker)
        return _fake_history(ticker)

    get_or_fetch_history(db, "005930", fetcher=counting)
    get_or_fetch_history(db, "005930", fetcher=counting)

    assert len(calls) == 1  # second call served from today's cache


def test_valuation_band_computes_percentile() -> None:
    band = valuation_band([8.0, 10.0, 14.0, 25.0], current=10.0)
    assert band is not None
    assert band["min"] == 8.0
    assert band["max"] == 25.0
    assert band["current"] == 10.0
    assert band["percentile"] == 50.0  # 2 of 4 values <= 10


def test_valuation_band_ignores_invalid_points() -> None:
    band = valuation_band([None, 0.0, -1.0, 12.0], current=12.0)
    assert band is not None
    assert band["min"] == 12.0
    assert band["max"] == 12.0


def test_valuation_band_returns_none_when_empty() -> None:
    assert valuation_band([None, 0.0, -3.0]) is None
