from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from backend.models import PriceBar
from backend.timezone import seoul_now

DAILY_INTERVAL = "1d"
WEEKLY_INTERVAL = "1w"
SUPPORTED_INTERVALS = {DAILY_INTERVAL, WEEKLY_INTERVAL}


def fetch_price_bars_df(
    db: Session,
    ticker: str,
    start: date,
    *,
    interval: str = DAILY_INTERVAL,
    end: date | None = None,
) -> pd.DataFrame | None:
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError(f"Unsupported price bar interval: {interval}")

    requested_start = start - timedelta(days=7)
    requested_end = end or seoul_now().date()
    cached = _load_cached_df(db, ticker, interval, requested_start, requested_end)
    refresh_start = _refresh_start(cached, requested_start, requested_end)

    if refresh_start is not None:
        try:
            fresh = _fetch_external_df(ticker, refresh_start, requested_end)
        except Exception:
            return None
        upsert_price_bars(db, ticker, interval, fresh)
        cached = _load_cached_df(db, ticker, interval, requested_start, requested_end)

    return cached.dropna(subset=["High", "Low"])


def upsert_price_bars(db: Session, ticker: str, interval: str, df: pd.DataFrame) -> int:
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError(f"Unsupported price bar interval: {interval}")
    if df.empty:
        return 0

    now = seoul_now()
    rows: list[dict[str, Any]] = []
    for ts, row in df.iterrows():
        bar_date = ts.date() if hasattr(ts, "date") else ts
        high = _float_or_none(row, "High")
        low = _float_or_none(row, "Low")
        open_ = _float_or_none(row, "Open")
        close = _float_or_none(row, "Close")
        if not _is_valid_ohlc(open_, high, low, close):
            continue

        volume = _float_or_none(row, "Volume")
        trading_value = _trading_value(row, close, volume)
        rows.append(
            {
                "ticker": ticker,
                "interval": interval,
                "bar_date": bar_date,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "trading_value": trading_value,
                "fetched_at": now,
            }
        )

    if not rows:
        return 0

    table = PriceBar.__table__
    dialect = db.get_bind().dialect.name
    update_columns = (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "trading_value",
        "fetched_at",
    )

    if dialect in {"mysql", "mariadb"}:
        stmt = mysql_insert(table).values(rows)
        stmt = stmt.on_duplicate_key_update(
            **{column: getattr(stmt.inserted, column) for column in update_columns}
        )
    elif dialect == "sqlite":
        stmt = sqlite_insert(table).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "interval", "bar_date"],
            set_={column: getattr(stmt.excluded, column) for column in update_columns},
        )
    else:
        raise RuntimeError(f"Unsupported price bar upsert dialect: {dialect}")

    db.execute(stmt)
    db.commit()
    return len(rows)


def _load_cached_df(
    db: Session,
    ticker: str,
    interval: str,
    start: date,
    end: date,
) -> pd.DataFrame:
    rows = db.scalars(
        select(PriceBar)
        .where(
            PriceBar.ticker == ticker,
            PriceBar.interval == interval,
            PriceBar.bar_date >= start,
            PriceBar.bar_date <= end,
        )
        .order_by(PriceBar.bar_date)
    ).all()
    return _rows_to_df(rows)


def _refresh_start(cached: pd.DataFrame, start: date, end: date) -> date | None:
    today = seoul_now().date()
    if cached.empty:
        return start

    first_cached = cached.index.min().date()
    if first_cached > start:
        return start

    last_cached = cached.index.max().date()
    if last_cached < end:
        return last_cached + timedelta(days=1)

    if start <= today <= end:
        return today

    return None


def _fetch_external_df(ticker: str, start: date, end: date) -> pd.DataFrame:
    import FinanceDataReader as fdr

    return fdr.DataReader(
        ticker,
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d"),
    )


def _rows_to_df(rows: list[PriceBar]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "TradingValue"])

    return pd.DataFrame(
        [
            {
                "Open": row.open,
                "High": row.high,
                "Low": row.low,
                "Close": row.close,
                "Volume": row.volume,
                "TradingValue": row.trading_value,
            }
            for row in rows
        ],
        index=pd.to_datetime([row.bar_date for row in rows]),
    )


def _float_or_none(row: Any, column: str) -> float | None:
    if column not in row or pd.isna(row[column]):
        return None
    return float(row[column])


def _is_valid_ohlc(
    open_: float | None,
    high: float | None,
    low: float | None,
    close: float | None,
) -> bool:
    if high is None or low is None or close is None:
        return False
    if high <= 0 or low <= 0 or close <= 0:
        return False
    if open_ is not None and open_ <= 0:
        return False
    return high >= low


def _trading_value(row: Any, close: float | None, volume: float | None) -> float | None:
    for column in ("TradingValue", "Value", "Amount", "거래대금"):
        value = _float_or_none(row, column)
        if value is not None:
            return value
    if close is None or volume is None:
        return None
    return close * volume
