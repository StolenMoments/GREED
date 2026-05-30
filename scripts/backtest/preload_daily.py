from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal, ensure_database_ready  # noqa: E402
from backend.models import PriceBar  # noqa: E402
from backend.price_bars import DAILY_INTERVAL, upsert_price_bars  # noqa: E402
from scripts.backtest.universe import DEFAULT_UNIVERSE_PATH, load_universe  # noqa: E402


DEFAULT_START = date(2011, 12, 19)
DEFAULT_DELAY_SECONDS = 1.5
DEFAULT_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 3.0
logger = logging.getLogger(__name__)
DailyFetcher = Callable[[str, date], pd.DataFrame]
Sleeper = Callable[[float], None]


@dataclass(slots=True)
class PreloadDailyResult:
    processed: int = 0
    skipped: int = 0
    upserted_rows: int = 0
    failed: list[tuple[str, str, str]] = field(default_factory=list)


def fetch_daily(ticker: str, start: date) -> pd.DataFrame:
    import FinanceDataReader as fdr

    return fdr.DataReader(ticker, start.strftime("%Y-%m-%d"))


def preload_daily_bars(
    db,
    *,
    universe: Iterable[tuple[str, str]],
    start: date = DEFAULT_START,
    fetcher: DailyFetcher = fetch_daily,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    retries: int = DEFAULT_RETRIES,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
    sleeper: Sleeper = time.sleep,
) -> PreloadDailyResult:
    result = PreloadDailyResult()
    rows = list(universe)
    for index, (ticker, name) in enumerate(rows):
        try:
            fetch_start, has_cache = _next_fetch_state(db, ticker, start)
            daily = _fetch_with_retries(
                ticker,
                fetch_start,
                fetcher=fetcher,
                retries=retries,
                retry_backoff_seconds=retry_backoff_seconds,
                sleeper=sleeper,
            )
            if daily is None or daily.empty:
                if has_cache:
                    logger.info("No new daily bars for %s %s from %s", ticker, name, fetch_start)
                    result.skipped += 1
                    continue
                raise RuntimeError("no daily data returned")
            result.upserted_rows += upsert_price_bars(db, ticker, DAILY_INTERVAL, daily)
            result.processed += 1
        except Exception as exc:
            message = str(exc)
            logger.warning("Failed to preload daily bars for %s %s: %s", ticker, name, message)
            result.failed.append((ticker, name, message))
        if delay_seconds > 0 and index < len(rows) - 1:
            sleeper(delay_seconds)
    return result


def _fetch_with_retries(
    ticker: str,
    start: date,
    *,
    fetcher: DailyFetcher,
    retries: int,
    retry_backoff_seconds: float,
    sleeper: Sleeper,
) -> pd.DataFrame:
    attempt = 0
    while True:
        try:
            return fetcher(ticker, start)
        except Exception:
            if attempt >= retries:
                raise
            wait = retry_backoff_seconds * (2**attempt)
            logger.info("Retrying daily fetch for %s after %.1fs", ticker, wait)
            if wait > 0:
                sleeper(wait)
            attempt += 1


def _next_fetch_state(db, ticker: str, default_start: date) -> tuple[date, bool]:
    latest = db.scalar(
        select(func.max(PriceBar.bar_date)).where(
            PriceBar.ticker == ticker,
            PriceBar.interval == DAILY_INTERVAL,
        )
    )
    if latest is None:
        return default_start, False
    return max(default_start, latest + timedelta(days=1)), True


def main() -> None:
    parser = argparse.ArgumentParser(description="Preload KOSPI200 daily OHLCV into price_bars(1d).")
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE_PATH))
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--retry-backoff", type=float, default=DEFAULT_RETRY_BACKOFF_SECONDS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ensure_database_ready()
    db = SessionLocal()
    try:
        result = preload_daily_bars(
            db,
            universe=load_universe(args.universe),
            start=date.fromisoformat(args.start),
            delay_seconds=args.delay,
            retries=args.retries,
            retry_backoff_seconds=args.retry_backoff,
        )
    finally:
        db.close()

    logger.info(
        "Daily preload finished: processed=%s skipped=%s upserted_rows=%s failed=%s",
        result.processed,
        result.skipped,
        result.upserted_rows,
        len(result.failed),
    )


if __name__ == "__main__":
    main()
