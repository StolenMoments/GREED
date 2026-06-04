from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal, ensure_database_ready  # noqa: E402
from backend.models import BacktestUniverseMember  # noqa: E402
from backend.price_bars import DAILY_INTERVAL, WEEKLY_INTERVAL, upsert_price_bars  # noqa: E402
from scripts.backtest.data import load_daily_ohlcv  # noqa: E402
from scripts.backtest.preload_daily import (  # noqa: E402
    DEFAULT_DELAY_SECONDS,
    DEFAULT_RETRIES,
    DEFAULT_RETRY_BACKOFF_SECONDS,
    DEFAULT_START,
    _fetch_with_retries,
    _next_fetch_state,
    fetch_daily,
)
from scripts.backtest.universe import load_active_universe, load_universe  # noqa: E402
from weekly_indicators import resample_weekly  # noqa: E402


logger = logging.getLogger(__name__)
DailyFetcher = Callable[[str, date], pd.DataFrame]
Sleeper = Callable[[float], None]


@dataclass(slots=True)
class PreloadPriceBarsResult:
    processed: int = 0
    skipped: int = 0
    daily_upserted_rows: int = 0
    weekly_upserted_rows: int = 0
    failed: list[tuple[str, str, str]] = field(default_factory=list)


def preload_price_bars(
    db,
    *,
    universe: Iterable[tuple[str, str]],
    start: date = DEFAULT_START,
    fetcher: DailyFetcher = fetch_daily,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    retries: int = DEFAULT_RETRIES,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
    sleeper: Sleeper = time.sleep,
) -> PreloadPriceBarsResult:
    result = PreloadPriceBarsResult()
    rows = list(universe)
    for index, (ticker, name) in enumerate(rows):
        try:
            fetch_start, has_daily_cache = _next_fetch_state(db, ticker, start)
            daily = _fetch_with_retries(
                ticker,
                fetch_start,
                fetcher=fetcher,
                retries=retries,
                retry_backoff_seconds=retry_backoff_seconds,
                sleeper=sleeper,
            )
            if daily is None or daily.empty:
                if not has_daily_cache:
                    raise RuntimeError("no daily data returned")
                logger.info("No new daily bars for %s %s from %s", ticker, name, fetch_start)
                result.skipped += 1
            else:
                result.daily_upserted_rows += upsert_price_bars(db, ticker, DAILY_INTERVAL, daily)

            cached_daily = load_daily_ohlcv(db, ticker)
            if cached_daily.empty:
                raise RuntimeError("no cached daily data available for weekly resample")
            weekly = resample_weekly(cached_daily)
            result.weekly_upserted_rows += upsert_price_bars(
                db,
                ticker,
                WEEKLY_INTERVAL,
                _to_upsert_df(weekly),
            )
            result.processed += 1
            logger.info(
                "Preloaded %s %s: daily_rows=%s weekly_rows=%s",
                ticker,
                name,
                0 if daily is None else len(daily),
                len(weekly),
            )
        except Exception as exc:
            message = str(exc)
            logger.warning("Failed to preload price bars for %s %s: %s", ticker, name, message)
            result.failed.append((ticker, name, message))
        if delay_seconds > 0 and index < len(rows) - 1:
            sleeper(delay_seconds)
    return result


def load_active_universe_for_source(db, source: str) -> list[tuple[str, str]]:
    rows = db.scalars(
        select(BacktestUniverseMember)
        .where(
            BacktestUniverseMember.active.is_(True),
            BacktestUniverseMember.market == "KR",
            BacktestUniverseMember.source == source,
        )
        .order_by(BacktestUniverseMember.sort_order, BacktestUniverseMember.ticker)
    ).all()
    if not rows:
        raise ValueError(f"No active backtest universe members found for source: {source}")
    return [(row.ticker, row.name) for row in rows]


def _to_upsert_df(weekly: pd.DataFrame) -> pd.DataFrame:
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preload daily and weekly OHLCV into price_bars for backtest universe members."
    )
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--universe", default=None, help="Optional CSV universe override.")
    parser.add_argument(
        "--source",
        default=None,
        help="Only preload active DB universe members with this source, e.g. kosdaq150-auto.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--retry-backoff", type=float, default=DEFAULT_RETRY_BACKOFF_SECONDS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ensure_database_ready()
    db = SessionLocal()
    try:
        if args.universe:
            universe = load_universe(args.universe)
        elif args.source:
            universe = load_active_universe_for_source(db, args.source)
        else:
            universe = load_active_universe(db)
        if args.limit is not None:
            universe = universe[: args.limit]
        result = preload_price_bars(
            db,
            universe=universe,
            start=date.fromisoformat(args.start),
            delay_seconds=args.delay,
            retries=args.retries,
            retry_backoff_seconds=args.retry_backoff,
        )
    finally:
        db.close()

    logger.info(
        "Price bar preload finished: processed=%s skipped=%s daily_upserted_rows=%s "
        "weekly_upserted_rows=%s failed=%s",
        result.processed,
        result.skipped,
        result.daily_upserted_rows,
        result.weekly_upserted_rows,
        len(result.failed),
    )


if __name__ == "__main__":
    main()
