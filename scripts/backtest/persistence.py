from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.models import BacktestRun, BacktestSignal, BacktestStat  # noqa: E402

from .engine import HORIZONS, SignalRecord, StatRow  # noqa: E402


def persist_run(
    db: Session,
    *,
    buy_threshold: int,
    warmup_weeks: int,
    ticker_count: int,
    records: list[SignalRecord],
    stats: list[StatRow],
    data_start: date | None,
    data_end: date | None,
    notes: str | None = None,
) -> int:
    run = BacktestRun(
        universe="KOSPI200",
        buy_threshold=buy_threshold,
        horizons=",".join(str(h) for h in HORIZONS),
        warmup_weeks=warmup_weeks,
        data_start=data_start,
        data_end=data_end,
        ticker_count=ticker_count,
        signal_count=len(records),
        notes=notes,
    )
    db.add(run)
    db.flush()  # run.id 확보

    for r in records:
        db.add(
            BacktestSignal(
                run_id=run.id,
                ticker=r.ticker,
                name=r.name,
                signal_date=r.signal_date,
                score=r.score,
                score_bucket=r.score_bucket,
                entry_date=r.entry_date,
                entry_price=r.entry_price,
                ret_4w=r.returns.get(4),
                ret_8w=r.returns.get(8),
                ret_12w=r.returns.get(12),
                ret_26w=r.returns.get(26),
            )
        )
    for s in stats:
        db.add(
            BacktestStat(
                run_id=run.id,
                horizon=s.horizon,
                score_bucket=s.score_bucket,
                count=s.count,
                censored_count=s.censored_count,
                win_rate=s.win_rate,
                mean=s.mean,
                median=s.median,
                std=s.std,
                p25=s.p25,
                p75=s.p75,
                min=s.min,
                max=s.max,
            )
        )
    db.commit()
    return run.id
