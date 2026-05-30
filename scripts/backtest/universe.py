from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import BacktestUniverseMember
from backend.tickers import normalize_ticker

DEFAULT_UNIVERSE_PATH = Path(__file__).resolve().parent / "kospi200.csv"


def load_universe(path: Path | str = DEFAULT_UNIVERSE_PATH) -> list[tuple[str, str]]:
    """Read a code,name CSV into normalized six-digit ticker/name pairs."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"KOSPI200 universe file does not exist: {p}\n"
            "Create a CSV with code,name columns at that path."
        )

    rows: list[tuple[str, str]] = []
    with p.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            if len(row) < 2:
                continue
            code = row[0].strip().zfill(6)
            name = row[1].strip()
            if code.isdigit() and len(code) == 6:
                rows.append((code, name))

    if not rows:
        raise ValueError(f"Universe file has no valid tickers: {p}")
    return rows


def normalize_korean_ticker(ticker: str) -> str:
    normalized = normalize_ticker(ticker)
    if not normalized.isdigit() or len(normalized) != 6:
        raise ValueError(f"6-digit Korean ticker required: {ticker}")
    return normalized


def load_active_universe(db: Session) -> list[tuple[str, str]]:
    rows = list(
        db.scalars(
            select(BacktestUniverseMember)
            .where(
                BacktestUniverseMember.active.is_(True),
                BacktestUniverseMember.market == "KR",
            )
            .order_by(BacktestUniverseMember.sort_order, BacktestUniverseMember.ticker)
        ).all()
    )
    if not rows:
        raise ValueError(
            "No active backtest universe members found. "
            "Import scripts/backtest/kospi200.csv or add tickers in the Backtest page."
        )
    return [(row.ticker, row.name) for row in rows]


def import_universe_csv(
    db: Session,
    path: Path | str = DEFAULT_UNIVERSE_PATH,
    *,
    source: str = "kospi200.csv",
) -> int:
    rows = load_universe(path)
    for sort_order, (ticker, name) in enumerate(rows):
        normalized = normalize_korean_ticker(ticker)
        existing = db.get(BacktestUniverseMember, normalized)
        if existing is None:
            db.add(
                BacktestUniverseMember(
                    ticker=normalized,
                    name=name,
                    market="KR",
                    active=True,
                    sort_order=sort_order,
                    source=source,
                )
            )
            continue

        existing.name = name
        existing.market = "KR"
        existing.active = True
        existing.sort_order = sort_order
        existing.source = source
    db.commit()
    return len(rows)
