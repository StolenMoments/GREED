from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.database import Base
from backend.models import PriceBar
from backend.price_bars import DAILY_INTERVAL, fetch_price_bars_df, upsert_price_bars


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def make_bars(rows: list[tuple[str, int, int, int, int, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume}
            for _, open_, high, low, close, volume in rows
        ],
        index=pd.to_datetime([day for day, *_ in rows]),
    )


def test_upsert_price_bars_computes_trading_value_and_updates_existing_row(
    db_session: Session,
) -> None:
    first = make_bars([("2026-05-13", 70000, 76000, 69000, 75000, 10)])
    second = make_bars([("2026-05-13", 71000, 77000, 70000, 76000, 20)])

    assert upsert_price_bars(db_session, "005930", DAILY_INTERVAL, first) == 1
    assert upsert_price_bars(db_session, "005930", DAILY_INTERVAL, second) == 1

    rows = db_session.scalars(select(PriceBar)).all()
    assert len(rows) == 1
    assert rows[0].high == 77000
    assert rows[0].trading_value == 76000 * 20


def test_fetch_price_bars_df_reuses_complete_past_cache(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.price_bars.seoul_now", lambda: datetime(2026, 5, 14, 12))
    upsert_price_bars(
        db_session,
        "005930",
        DAILY_INTERVAL,
        make_bars(
            [
                ("2026-05-06", 70000, 76000, 69000, 75000, 10),
                ("2026-05-13", 71000, 77000, 70000, 76000, 20),
            ]
        ),
    )

    def fail_fetch(ticker: str, start: date, end: date) -> pd.DataFrame:
        raise AssertionError("past cache should not fetch")

    monkeypatch.setattr("backend.price_bars._fetch_external_df", fail_fetch)

    df = fetch_price_bars_df(db_session, "005930", date(2026, 5, 13), end=date(2026, 5, 13))

    assert df is not None
    assert list(df["High"]) == [76000, 77000]


def test_fetch_price_bars_df_refreshes_today_only_when_past_cache_exists(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.price_bars.seoul_now", lambda: datetime(2026, 5, 14, 12))
    upsert_price_bars(
        db_session,
        "005930",
        DAILY_INTERVAL,
        make_bars(
            [
                ("2026-05-06", 70000, 76000, 69000, 75000, 10),
                ("2026-05-13", 71000, 77000, 70000, 76000, 20),
            ]
        ),
    )
    calls: list[tuple[date, date]] = []

    def fake_fetch(ticker: str, start: date, end: date) -> pd.DataFrame:
        calls.append((start, end))
        return make_bars([("2026-05-14", 72000, 83000, 71000, 82000, 30)])

    monkeypatch.setattr("backend.price_bars._fetch_external_df", fake_fetch)

    df = fetch_price_bars_df(db_session, "005930", date(2026, 5, 13), end=date(2026, 5, 14))

    assert calls == [(date(2026, 5, 14), date(2026, 5, 14))]
    assert df is not None
    assert list(df["High"]) == [76000, 77000, 83000]


def test_fetch_price_bars_df_refreshes_from_cache_tail_before_today(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.price_bars.seoul_now", lambda: datetime(2026, 5, 14, 12))
    upsert_price_bars(
        db_session,
        "005930",
        DAILY_INTERVAL,
        make_bars(
            [
                ("2026-05-06", 70000, 76000, 69000, 75000, 10),
                ("2026-05-10", 71000, 77000, 70000, 76000, 20),
            ]
        ),
    )
    calls: list[tuple[date, date]] = []

    def fake_fetch(ticker: str, start: date, end: date) -> pd.DataFrame:
        calls.append((start, end))
        return make_bars(
            [
                ("2026-05-11", 72000, 78000, 71000, 77000, 30),
                ("2026-05-12", 73000, 79000, 72000, 78000, 40),
                ("2026-05-13", 74000, 80000, 73000, 79000, 50),
                ("2026-05-14", 75000, 83000, 74000, 82000, 60),
            ]
        )

    monkeypatch.setattr("backend.price_bars._fetch_external_df", fake_fetch)

    df = fetch_price_bars_df(db_session, "005930", date(2026, 5, 13), end=date(2026, 5, 14))

    assert calls == [(date(2026, 5, 11), date(2026, 5, 14))]
    assert df is not None
    assert list(df["High"]) == [76000, 77000, 78000, 79000, 80000, 83000]


def test_fetch_price_bars_df_returns_none_when_required_refresh_fails(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("backend.price_bars.seoul_now", lambda: datetime(2026, 5, 14, 12))
    upsert_price_bars(
        db_session,
        "005930",
        DAILY_INTERVAL,
        make_bars(
            [
                ("2026-05-06", 70000, 76000, 69000, 75000, 10),
                ("2026-05-13", 71000, 77000, 70000, 76000, 20),
            ]
        ),
    )

    def fail_fetch(ticker: str, start: date, end: date) -> pd.DataFrame:
        raise RuntimeError("source unavailable")

    monkeypatch.setattr("backend.price_bars._fetch_external_df", fail_fetch)

    df = fetch_price_bars_df(db_session, "005930", date(2026, 5, 13), end=date(2026, 5, 14))

    assert df is None
