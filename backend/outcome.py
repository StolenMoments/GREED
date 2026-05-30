from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.models import Analysis
from backend.price_bars import fetch_price_bars_df
from backend.tickers import normalize_ticker

OUTCOME_TARGET = "목표달성"
OUTCOME_STOP = "손절"
OUTCOME_ONGOING = "진행중"
OUTCOME_NA = "판정불가"
TERMINAL_OUTCOMES = {OUTCOME_TARGET, OUTCOME_STOP, OUTCOME_NA}


def evaluate_outcome(
    analysis: Analysis,
    df,
) -> tuple[str, date | None, float | None]:
    """Returns (outcome, outcome_date, outcome_price) by scanning daily OHLCV df."""
    if analysis.target_price is None and analysis.stop_loss is None:
        return OUTCOME_NA, None, None

    analysis_date = analysis.created_at.date()

    for ts, row in df.iterrows():
        trade_date: date = ts.date() if hasattr(ts, "date") else ts
        if trade_date < analysis_date:
            continue

        hit_stop = analysis.stop_loss is not None and float(row["Low"]) <= analysis.stop_loss
        hit_target = analysis.target_price is not None and float(row["High"]) >= analysis.target_price

        if hit_stop:
            return OUTCOME_STOP, trade_date, float(row["Low"])
        if hit_target:
            return OUTCOME_TARGET, trade_date, float(row["High"])

    return OUTCOME_ONGOING, None, None


def fetch_daily_df(ticker: str, start: date, db: Session | None = None):
    if db is not None:
        return fetch_price_bars_df(db, ticker, start)

    import FinanceDataReader as fdr

    start_str = (start - timedelta(days=7)).strftime("%Y-%m-%d")
    end_str = date.today().strftime("%Y-%m-%d")
    return fdr.DataReader(ticker, start_str, end_str).dropna(subset=["High", "Low"])


def should_evaluate_outcome(analysis: Analysis, force: bool = False) -> bool:
    return force or analysis.outcome not in TERMINAL_OUTCOMES


def evaluate_single_outcome(db: Session, analysis: Analysis, force: bool = False) -> bool:
    if not should_evaluate_outcome(analysis, force=force):
        return False

    if analysis.target_price is None and analysis.stop_loss is None:
        analysis.outcome = OUTCOME_NA
        analysis.outcome_date = None
        analysis.outcome_price = None
        db.commit()
        db.refresh(analysis)
        return True

    try:
        df = fetch_daily_df(normalize_ticker(analysis.ticker), analysis.created_at.date(), db=db)
    except Exception:
        return False

    if df is None or df.empty:
        return False

    outcome, outcome_date, outcome_price = evaluate_outcome(analysis, df)
    analysis.outcome = outcome
    analysis.outcome_date = outcome_date
    analysis.outcome_price = outcome_price
    db.commit()
    db.refresh(analysis)
    return True


def run_evaluate_outcomes(db: Session, force: bool = False) -> dict[str, int]:
    stmt = select(Analysis)
    if not force:
        stmt = stmt.where(or_(Analysis.outcome.is_(None), Analysis.outcome == OUTCOME_ONGOING))
    pending = list(db.scalars(stmt).all())

    evaluated = 0
    skipped = 0
    by_ticker: dict[str, list[Analysis]] = defaultdict(list)

    for analysis in pending:
        if analysis.target_price is None and analysis.stop_loss is None:
            analysis.outcome = OUTCOME_NA
            analysis.outcome_date = None
            analysis.outcome_price = None
            evaluated += 1
        else:
            by_ticker[normalize_ticker(analysis.ticker)].append(analysis)
    fetch_starts = {
        ticker: min(a.created_at.date() for a in analyses)
        for ticker, analyses in by_ticker.items()
    }

    def _fetch(ticker: str, earliest: date):
        try:
            df = fetch_daily_df(ticker, earliest, db=db)
        except Exception:
            return ticker, None
        if df is None or df.empty:
            return ticker, None
        return ticker, df

    for ticker, earliest in fetch_starts.items():
        ticker, df = _fetch(ticker, earliest)
        analyses = by_ticker[ticker]
        if df is None:
            skipped += len(analyses)
            continue
        for analysis in analyses:
            outcome, outcome_date, outcome_price = evaluate_outcome(analysis, df)
            analysis.outcome = outcome
            analysis.outcome_date = outcome_date
            analysis.outcome_price = outcome_price
            evaluated += 1
        db.commit()

    db.commit()
    return {"evaluated": evaluated, "skipped": skipped}
