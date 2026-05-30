from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.database import Base
from backend.models import PriceBar
from backend.price_bars import DAILY_INTERVAL, WEEKLY_INTERVAL, fetch_price_bars_df, upsert_price_bars
from scripts.backtest.data import load_daily_ohlcv


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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = make_bars([("2026-05-13", 70000, 76000, 69000, 75000, 10)])
    second = make_bars([("2026-05-13", 71000, 77000, 70000, 76000, 20)])

    assert upsert_price_bars(db_session, "005930", DAILY_INTERVAL, first) == 1

    def fail_merge(*args, **kwargs):
        raise AssertionError("price bar upsert must not use ORM merge")

    monkeypatch.setattr(db_session, "merge", fail_merge)

    assert upsert_price_bars(db_session, "005930", DAILY_INTERVAL, second) == 1

    rows = db_session.scalars(select(PriceBar)).all()
    assert len(rows) == 1
    assert rows[0].high == 77000
    assert rows[0].trading_value == 76000 * 20


def test_upsert_price_bars_updates_existing_weekly_row_without_merge(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = make_bars([("2026-05-13", 70000, 76000, 69000, 75000, 10)])
    second = make_bars([("2026-05-13", 71000, 77000, 70000, 76000, 20)])

    assert upsert_price_bars(db_session, "005930", WEEKLY_INTERVAL, first) == 1

    def fail_merge(*args, **kwargs):
        raise AssertionError("weekly price bar upsert must not use ORM merge")

    monkeypatch.setattr(db_session, "merge", fail_merge)

    assert upsert_price_bars(db_session, "005930", WEEKLY_INTERVAL, second) == 1

    rows = db_session.scalars(select(PriceBar)).all()
    assert len(rows) == 1
    assert rows[0].interval == WEEKLY_INTERVAL
    assert rows[0].high == 77000


def test_upsert_price_bars_skips_invalid_ohlc_rows(db_session: Session) -> None:
    df = make_bars(
        [
            ("2026-05-11", 70000, 76000, 69000, 75000, 10),
            ("2026-05-12", 0, 76000, 69000, 75000, 10),
            ("2026-05-13", 70000, 0, 69000, 75000, 10),
            ("2026-05-14", 70000, 76000, 0, 75000, 10),
            ("2026-05-15", 70000, 76000, 69000, 0, 10),
            ("2026-05-18", 70000, 68000, 69000, 75000, 10),
        ]
    )

    assert upsert_price_bars(db_session, "005930", DAILY_INTERVAL, df) == 1

    rows = db_session.scalars(select(PriceBar).order_by(PriceBar.bar_date)).all()
    assert [row.bar_date for row in rows] == [date(2026, 5, 11)]


def test_upsert_price_bars_allows_missing_open_for_legacy_sources(db_session: Session) -> None:
    df = pd.DataFrame(
        [{"High": 76000, "Low": 69000, "Close": 75000, "Volume": 10}],
        index=pd.to_datetime(["2026-05-11"]),
    )

    assert upsert_price_bars(db_session, "005930", DAILY_INTERVAL, df) == 1

    row = db_session.scalar(select(PriceBar))
    assert row is not None
    assert row.open is None


def test_load_daily_ohlcv_skips_existing_invalid_ohlc_rows(db_session: Session) -> None:
    fetched_at = datetime(2026, 5, 19, 12)
    db_session.add_all(
        [
            PriceBar(
                ticker="005930",
                interval=DAILY_INTERVAL,
                bar_date=date(2026, 5, 11),
                open=70000,
                high=76000,
                low=69000,
                close=75000,
                volume=10,
                trading_value=750000,
                fetched_at=fetched_at,
            ),
            PriceBar(
                ticker="005930",
                interval=DAILY_INTERVAL,
                bar_date=date(2026, 5, 12),
                open=0,
                high=0,
                low=0,
                close=75000,
                volume=0,
                trading_value=0,
                fetched_at=fetched_at,
            ),
            PriceBar(
                ticker="005930",
                interval=DAILY_INTERVAL,
                bar_date=date(2026, 5, 13),
                open=70000,
                high=68000,
                low=69000,
                close=75000,
                volume=10,
                trading_value=750000,
                fetched_at=fetched_at,
            ),
        ]
    )
    db_session.commit()

    df = load_daily_ohlcv(db_session, "005930")

    assert list(df.index.date) == [date(2026, 5, 11)]


def test_load_daily_ohlcv_fetches_and_caches_when_missing(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetched = make_bars(
        [
            ("2026-05-11", 70000, 76000, 69000, 75000, 10),
            ("2026-05-12", 71000, 77000, 70000, 76000, 20),
        ]
    )

    monkeypatch.setattr("scripts.backtest.data._fetch_daily_max", lambda ticker: fetched)

    df = load_daily_ohlcv(db_session, "083450", fetch_missing=True)

    assert list(df.index.date) == [date(2026, 5, 11), date(2026, 5, 12)]
    assert list(df["close"]) == [75000, 76000]

    rows = db_session.scalars(
        select(PriceBar)
        .where(PriceBar.ticker == "083450", PriceBar.interval == DAILY_INTERVAL)
        .order_by(PriceBar.bar_date)
    ).all()
    assert [row.bar_date for row in rows] == [date(2026, 5, 11), date(2026, 5, 12)]


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
