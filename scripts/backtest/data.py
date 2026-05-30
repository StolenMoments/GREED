from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from backend.models import PriceBar  # noqa: E402
from backend.price_bars import DAILY_INTERVAL, WEEKLY_INTERVAL, upsert_price_bars  # noqa: E402
from weekly_indicators import resample_weekly  # noqa: E402

MIN_HISTORY_WEEKS = 120 + 26 + 60


def _load_cached_weekly(db: Session, ticker: str) -> pd.DataFrame:
    rows = db.scalars(
        select(PriceBar)
        .where(PriceBar.ticker == ticker, PriceBar.interval == WEEKLY_INTERVAL)
        .order_by(PriceBar.bar_date)
    ).all()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        {
            "open": [r.open for r in rows],
            "high": [r.high for r in rows],
            "low": [r.low for r in rows],
            "close": [r.close for r in rows],
            "volume": [r.volume for r in rows],
            "trading_value": [r.trading_value for r in rows],
        },
        index=pd.to_datetime([r.bar_date for r in rows]),
    )
    df.index.name = "date"
    return df.dropna(subset=["close"])


def load_daily_ohlcv(db: Session, ticker: str) -> pd.DataFrame:
    rows = db.scalars(
        select(PriceBar)
        .where(PriceBar.ticker == ticker, PriceBar.interval == DAILY_INTERVAL)
        .order_by(PriceBar.bar_date)
    ).all()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(
        {
            "open": [r.open for r in rows],
            "high": [r.high for r in rows],
            "low": [r.low for r in rows],
            "close": [r.close for r in rows],
            "volume": [r.volume for r in rows],
            "trading_value": [r.trading_value for r in rows],
        },
        index=pd.to_datetime([r.bar_date for r in rows]),
    )
    df.index.name = "date"
    return valid_daily_ohlcv(df)


def valid_daily_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    price = df.dropna(subset=["high", "low", "close"])
    valid = (
        (price["high"] > 0)
        & (price["low"] > 0)
        & (price["close"] > 0)
        & (price["high"] >= price["low"])
    )
    if "open" in price:
        valid &= price["open"].isna() | (price["open"] > 0)
    return price.loc[valid]


def _fetch_daily_max(ticker: str) -> pd.DataFrame | None:
    import FinanceDataReader as fdr

    try:
        df = fdr.DataReader(ticker)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    return df


def _to_upsert_df(weekly: pd.DataFrame) -> pd.DataFrame:
    """Convert resample_weekly output to columns consumed by upsert_price_bars."""
    return pd.DataFrame(
        {
            "Open": weekly["open"],
            "High": weekly["high"],
            "Low": weekly["low"],
            "Close": weekly["close"],
            "Volume": weekly["volume"],
            "TradingValue": weekly["trading_value"],
        },
        index=weekly.index,
    )


def load_weekly_ohlcv(db: Session, ticker: str) -> pd.DataFrame:
    """Return weekly OHLCV with lower-case columns, using price_bars(1w) first."""
    cached = _load_cached_weekly(db, ticker)
    if len(cached) >= MIN_HISTORY_WEEKS:
        return cached

    daily = _fetch_daily_max(ticker)
    if daily is None:
        return cached

    weekly = resample_weekly(daily)
    upsert_price_bars(db, ticker, WEEKLY_INTERVAL, _to_upsert_df(weekly))
    return _load_cached_weekly(db, ticker)
