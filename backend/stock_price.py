from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from sqlalchemy.orm import Session

from backend import crud
from backend.models import StockPrice
from backend.tickers import normalize_ticker


def fetch_latest_close(ticker: str) -> tuple[date, float] | None:
    import FinanceDataReader as fdr

    ticker = normalize_ticker(ticker)
    start = (date.today() - timedelta(days=10)).strftime("%Y-%m-%d")
    end = date.today().strftime("%Y-%m-%d")
    df = fdr.DataReader(ticker, start, end)
    if df.empty:
        return None
    last = df.iloc[-1]
    price_date = last.name.date() if hasattr(last.name, "date") else date.today()
    return price_date, float(last["Close"])


def fetch_and_store_latest_close(
    db: Session,
    ticker: str,
    fetcher: Callable[[str], tuple[date, float] | None] = fetch_latest_close,
) -> StockPrice | None:
    ticker = normalize_ticker(ticker)
    result = fetcher(ticker)
    if result is None:
        return None

    price_date, close_price = result
    return crud.upsert_stock_price(db, ticker, price_date, close_price)
