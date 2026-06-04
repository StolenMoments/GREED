from __future__ import annotations

import argparse
from datetime import date
import re
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.database import SessionLocal, ensure_database_ready  # noqa: E402
from backend.models import BacktestUniverseMember  # noqa: E402
from scripts.backtest.universe import normalize_korean_ticker  # noqa: E402


KOSDAQ150_SOURCE = "kosdaq150-auto"
EXPECTED_KOSDAQ150_COUNT = 150


def _stock_client():
    from pykrx import stock

    return stock


def normalize_index_name(name: str) -> str:
    return re.sub(r"\s+", "", name or "")


def normalize_krx_member_ticker(ticker: str) -> str:
    raw = str(ticker).strip().upper()
    if raw.isdigit():
        return normalize_korean_ticker(raw)
    if len(raw) == 6 and raw.isalnum():
        return raw
    raise ValueError(f"6-character KRX ticker required: {ticker}")


def find_kosdaq150_index_code(target_date: str, *, stock_client=None) -> str:
    stock = stock_client or _stock_client()
    for index_code in stock.get_index_ticker_list(target_date, market="KOSDAQ"):
        if normalize_index_name(stock.get_index_ticker_name(index_code)) == "코스닥150":
            return str(index_code)
    raise ValueError(f"KOSDAQ150 index code not found for {target_date}")


def fetch_kosdaq150_members(
    target_date: str,
    *,
    stock_client=None,
) -> list[tuple[str, str]]:
    stock = stock_client or _stock_client()
    index_code = find_kosdaq150_index_code(target_date, stock_client=stock)
    tickers = stock.get_index_portfolio_deposit_file(
        index_code,
        target_date,
        alternative=True,
    )
    rows: list[tuple[str, str]] = []
    for ticker in tickers:
        normalized = normalize_krx_member_ticker(str(ticker))
        rows.append((normalized, stock.get_market_ticker_name(normalized).strip()))
    if len(rows) != EXPECTED_KOSDAQ150_COUNT:
        raise ValueError(
            f"Expected 150 KOSDAQ150 members for {target_date}, fetched {len(rows)}"
        )
    return rows


def sync_kosdaq150_members(
    db: Session,
    target_date: str,
    *,
    stock_client=None,
) -> int:
    rows = fetch_kosdaq150_members(target_date, stock_client=stock_client)
    max_sort_order = db.scalar(select(func.max(BacktestUniverseMember.sort_order)))
    next_sort_order = (max_sort_order + 1) if max_sort_order is not None else 0

    for ticker, name in rows:
        existing = db.get(BacktestUniverseMember, ticker)
        if existing is None:
            db.add(
                BacktestUniverseMember(
                    ticker=ticker,
                    name=name,
                    market="KR",
                    active=True,
                    sort_order=next_sort_order,
                    source=KOSDAQ150_SOURCE,
                )
            )
            next_sort_order += 1
            continue

        existing.name = name
        existing.market = "KR"
        existing.active = True
        existing.source = KOSDAQ150_SOURCE

    db.commit()
    return len(rows)


def _default_date() -> str:
    return date.today().strftime("%Y%m%d")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch KOSDAQ150 constituents from KRX and upsert them into the backtest universe."
    )
    parser.add_argument("--date", default=_default_date(), help="KRX date in YYYYMMDD format.")
    args = parser.parse_args()

    ensure_database_ready()
    stock = _stock_client()
    index_code = find_kosdaq150_index_code(args.date, stock_client=stock)
    print(f"Found KOSDAQ150 index code: {index_code}")

    db = SessionLocal()
    try:
        count = sync_kosdaq150_members(db, args.date, stock_client=stock)
        active_count = db.scalar(
            select(func.count())
            .select_from(BacktestUniverseMember)
            .where(BacktestUniverseMember.active.is_(True))
        )
        print(f"Fetched {count} KOSDAQ150 members")
        print(f"Inserted/updated {count} backtest universe members")
        print(f"Active backtest universe count after sync: {active_count}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
