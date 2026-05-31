from __future__ import annotations

import logging
import math
from collections.abc import Callable
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from backend import crud
from backend.models import FundamentalHistory, FundamentalSnapshot
from backend.tickers import normalize_ticker
from backend.timezone import seoul_now

logger = logging.getLogger(__name__)

# Snapshot dict keys produced by a fetcher and consumed by the store helper.
SnapshotData = dict[str, object]
Fetcher = Callable[[str], "SnapshotData | None"]
HistoryFetcher = Callable[[str], "list[dict[str, object]]"]
HISTORY_YEARS = 3


def _clean(value: object) -> float | None:
    """Coerce a pykrx/pandas value to a finite float, mapping NaN/inf/invalid to None."""
    if value is None:
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _parse_yyyymmdd(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def fetch_fundamental_snapshot(ticker: str) -> SnapshotData | None:
    """Fetch the latest KR fundamental snapshot for a ticker via pykrx.

    Returns None when no data is available (e.g. unsupported ticker). pykrx is
    imported lazily so the module stays importable in environments without it.
    """
    from pykrx import stock

    ticker = normalize_ticker(ticker)
    day = stock.get_nearest_business_day_in_a_week()

    fundamental = stock.get_market_fundamental(day, day, ticker)
    if fundamental is None or fundamental.empty:
        return None
    row = fundamental.iloc[-1]

    market_cap: float | None = None
    try:
        cap = stock.get_market_cap(day, day, ticker)
        if cap is not None and not cap.empty:
            market_cap = _clean(cap.iloc[-1].get("시가총액"))
    except Exception as exc:  # market cap is best-effort, never fail the snapshot
        logger.warning("market_cap fetch failed for %s: %s", ticker, exc)

    return {
        "snapshot_date": _parse_yyyymmdd(day),
        "per": _clean(row.get("PER")),
        "pbr": _clean(row.get("PBR")),
        "eps": _clean(row.get("EPS")),
        "bps": _clean(row.get("BPS")),
        "div_yield": _clean(row.get("DIV")),
        "market_cap": market_cap,
    }


def fetch_and_store_fundamental(
    db: Session,
    ticker: str,
    fetcher: Fetcher = fetch_fundamental_snapshot,
) -> FundamentalSnapshot | None:
    ticker = normalize_ticker(ticker)
    data = fetcher(ticker)
    if data is None:
        return None
    snapshot_date = data.get("snapshot_date") or seoul_now().date()
    return crud.upsert_fundamental_snapshot(
        db,
        ticker,
        snapshot_date=snapshot_date,  # type: ignore[arg-type]
        per=data.get("per"),  # type: ignore[arg-type]
        pbr=data.get("pbr"),  # type: ignore[arg-type]
        eps=data.get("eps"),  # type: ignore[arg-type]
        bps=data.get("bps"),  # type: ignore[arg-type]
        div_yield=data.get("div_yield"),  # type: ignore[arg-type]
        market_cap=data.get("market_cap"),  # type: ignore[arg-type]
    )


def _is_fresh(fetched_at: datetime | None) -> bool:
    if fetched_at is None:
        return False
    return fetched_at.date() == seoul_now().date()


def get_or_fetch_fundamental(
    db: Session,
    ticker: str,
    fetcher: Fetcher = fetch_fundamental_snapshot,
) -> FundamentalSnapshot | None:
    """Return today's cached snapshot, otherwise fetch and store a fresh one.

    Falls back to a stale cached snapshot if a fresh fetch yields nothing.
    """
    ticker = normalize_ticker(ticker)
    existing = crud.get_fundamental_snapshot(db, ticker)
    if existing is not None and _is_fresh(existing.fetched_at):
        return existing
    fetched = fetch_and_store_fundamental(db, ticker, fetcher=fetcher)
    return fetched if fetched is not None else existing


def fetch_fundamental_history(
    ticker: str,
    years: int = HISTORY_YEARS,
    freq: str = "m",
) -> list[dict[str, object]]:
    """Fetch a KR fundamental time series (PER/PBR/EPS/BPS/DIV) via pykrx.

    Returns a chronological list of point dicts. pykrx is imported lazily.
    """
    from pykrx import stock

    ticker = normalize_ticker(ticker)
    end = seoul_now().date()
    start = end - timedelta(days=365 * years + 7)
    df = stock.get_market_fundamental_by_date(
        start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), ticker, freq=freq
    )
    if df is None or df.empty:
        return []

    rows: list[dict[str, object]] = []
    for index, row in df.iterrows():
        snapshot_date = index.date() if hasattr(index, "date") else index
        rows.append(
            {
                "snapshot_date": snapshot_date,
                "per": _clean(row.get("PER")),
                "pbr": _clean(row.get("PBR")),
                "eps": _clean(row.get("EPS")),
                "bps": _clean(row.get("BPS")),
                "div_yield": _clean(row.get("DIV")),
            }
        )
    return rows


def fetch_and_store_history(
    db: Session,
    ticker: str,
    fetcher: HistoryFetcher = fetch_fundamental_history,
) -> int:
    ticker = normalize_ticker(ticker)
    rows = fetcher(ticker)
    if not rows:
        return 0
    return crud.upsert_fundamental_history_rows(db, ticker, rows)


def get_or_fetch_history(
    db: Session,
    ticker: str,
    fetcher: HistoryFetcher = fetch_fundamental_history,
) -> list[FundamentalHistory]:
    """Return today's cached history, otherwise refetch the full range and store it.

    Falls back to stale cached rows if a fresh fetch yields nothing.
    """
    ticker = normalize_ticker(ticker)
    existing = crud.get_fundamental_history(db, ticker)
    if existing:
        latest_fetch = max((r.fetched_at for r in existing if r.fetched_at), default=None)
        if latest_fetch is not None and latest_fetch.date() == seoul_now().date():
            return existing
    rows = fetcher(ticker)
    if rows:
        crud.upsert_fundamental_history_rows(db, ticker, rows)
        return crud.get_fundamental_history(db, ticker)
    return existing


def valuation_band(
    values: list[float | None],
    current: float | None = None,
) -> dict[str, float] | None:
    """Min/median/max and the current value's percentile within a metric series.

    Ignores non-positive/None points (invalid PER/PBR). Returns None if empty.
    """
    nums = [float(v) for v in values if v is not None and v > 0]
    if not nums:
        return None
    ordered = sorted(nums)
    n = len(ordered)
    cur = current if (current is not None and current > 0) else nums[-1]
    rank = sum(1 for v in ordered if v <= cur)
    percentile = rank / n * 100.0
    if n % 2:
        median = ordered[n // 2]
    else:
        median = (ordered[n // 2 - 1] + ordered[n // 2]) / 2.0
    return {
        "min": ordered[0],
        "max": ordered[-1],
        "median": median,
        "current": cur,
        "percentile": percentile,
    }
