from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from rule_scorer.features import _apply_confirmation_shift, extract_features_asof  # noqa: E402
from rule_scorer.score import score_features  # noqa: E402
from weekly_indicators import add_all_indicators, append_future_cloud  # noqa: E402


HORIZONS: tuple[int, ...] = (4, 8, 12, 26)
WARMUP_WEEKS = 120
BUCKETS: tuple[str, ...] = ("4-5", "6-7", "8+", "ALL")


@dataclass(slots=True)
class SignalRecord:
    ticker: str
    name: str
    signal_date: date
    score: int
    score_bucket: str
    entry_date: date | None
    entry_price: float
    returns: dict[int, float | None] = field(default_factory=dict)
    exit_date: date | None = None
    exit_reason: str | None = None
    exit_price: float | None = None
    event_return: float | None = None
    days_held: int | None = None


@dataclass(slots=True)
class StatRow:
    horizon: int
    score_bucket: str
    count: int
    censored_count: int
    win_rate: float | None
    mean: float | None
    median: float | None
    std: float | None
    p25: float | None
    p75: float | None
    min: float | None
    max: float | None


@dataclass(slots=True)
class Span2BacktestResult:
    records: list[SignalRecord] = field(default_factory=list)
    stats: list[StatRow] = field(default_factory=list)
    ticker_count: int = 0
    data_start: date | None = None
    data_end: date | None = None


def score_bucket(total: int) -> str:
    if total >= 8:
        return "8+"
    if total >= 6:
        return "6-7"
    return "4-5"


def _to_date(value) -> date:
    return pd.to_datetime(value).date()


def _f(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def build_combined(weekly_ohlcv: pd.DataFrame, ticker: str, name: str) -> pd.DataFrame:
    """Return indicator + future-cloud frame expected by extract_features_asof."""
    df = add_all_indicators(weekly_ohlcv.copy())
    df = append_future_cloud(df).reset_index()
    df["date"] = df["date"].astype(str).str.slice(0, 10)
    df["ticker"] = ticker
    df["name"] = name
    return _apply_confirmation_shift(df)


def run_ticker(
    combined: pd.DataFrame,
    *,
    horizons: tuple[int, ...] = HORIZONS,
    warmup: int = WARMUP_WEEKS,
) -> list[SignalRecord]:
    price = combined[combined["close"].notna()].reset_index(drop=True)
    n = len(price)
    records: list[SignalRecord] = []
    last_entry_i = n - 2

    for i in range(warmup, last_entry_i + 1):
        feats = extract_features_asof(combined, i)
        result = score_features(feats)
        if result.judgment != "매수":
            continue

        entry_price = _f(price["open"].iloc[i + 1])
        if entry_price is None or entry_price <= 0:
            continue

        returns: dict[int, float | None] = {}
        for horizon in horizons:
            exit_i = i + horizon
            exit_close = _f(price["close"].iloc[exit_i]) if exit_i < n else None
            returns[horizon] = (exit_close / entry_price - 1) if exit_close is not None else None

        records.append(
            SignalRecord(
                ticker=feats.ticker,
                name=feats.name,
                signal_date=_to_date(price["date"].iloc[i]),
                score=result.total,
                score_bucket=score_bucket(result.total),
                entry_date=_to_date(price["date"].iloc[i + 1]),
                entry_price=entry_price,
                returns=returns,
            )
        )

    return records


def run_span2_breakout_ticker(
    combined: pd.DataFrame,
    *,
    warmup: int = WARMUP_WEEKS,
) -> list[SignalRecord]:
    price = combined[combined["close"].notna()].reset_index(drop=True)
    n = len(price)
    records: list[SignalRecord] = []
    i = warmup

    while i < n:
        if i == 0:
            i += 1
            continue

        prev_close = _f(price["close"].iloc[i - 1])
        close = _f(price["close"].iloc[i])
        span2 = _f(price["ichi_lead2"].iloc[i]) if "ichi_lead2" in price else None
        cloud_top = _f(price["cloud_top"].iloc[i]) if "cloud_top" in price else None
        cloud_bottom = _f(price["cloud_bottom"].iloc[i]) if "cloud_bottom" in price else None
        if (
            prev_close is None
            or close is None
            or span2 is None
            or cloud_top is None
            or cloud_bottom is None
            or close <= 0
            or not (prev_close <= span2 < close and close > cloud_top)
        ):
            i += 1
            continue

        entry_date = _to_date(price["date"].iloc[i])
        entry_price = close
        exit_i = n - 1
        exit_reason = "open"
        exit_price = _f(price["close"].iloc[exit_i])

        for j in range(i + 1, n):
            hold_close = _f(price["close"].iloc[j])
            hold_bottom = _f(price["cloud_bottom"].iloc[j]) if "cloud_bottom" in price else None
            if hold_close is None or hold_bottom is None:
                continue
            if hold_close < hold_bottom:
                exit_i = j
                exit_reason = "stop"
                exit_price = hold_close
                break

        exit_date = _to_date(price["date"].iloc[exit_i]) if exit_price is not None else None
        records.append(
            SignalRecord(
                ticker=str(price["ticker"].iloc[i]),
                name=str(price["name"].iloc[i]),
                signal_date=entry_date,
                score=1,
                score_bucket="span2",
                entry_date=entry_date,
                entry_price=entry_price,
                returns={},
                exit_date=exit_date,
                exit_reason=exit_reason,
                exit_price=exit_price,
                event_return=(exit_price / entry_price - 1) if exit_price is not None else None,
                days_held=(exit_date - entry_date).days if exit_date is not None else None,
            )
        )
        i = exit_i + 1

    return records


def run_span2_breakout_backtest(
    db,
    *,
    warmup: int = WARMUP_WEEKS,
    universe_path=None,
) -> Span2BacktestResult:
    from scripts.backtest.data import load_weekly_ohlcv
    from scripts.backtest.universe import load_active_universe, load_universe

    records: list[SignalRecord] = []
    data_start: date | None = None
    data_end: date | None = None
    processed = 0
    universe = load_universe(universe_path) if universe_path is not None else load_active_universe(db)

    for code, name in universe:
        weekly = load_weekly_ohlcv(db, code)
        if weekly.empty or len(weekly) <= warmup + 1:
            continue

        combined = build_combined(weekly, code, name)
        records.extend(run_span2_breakout_ticker(combined, warmup=warmup))
        processed += 1
        first = weekly.index.min().date()
        last = weekly.index.max().date()
        data_start = first if data_start is None else min(data_start, first)
        data_end = last if data_end is None else max(data_end, last)

    return Span2BacktestResult(
        records=records,
        stats=[],
        ticker_count=processed,
        data_start=data_start,
        data_end=data_end,
    )


def _stat_row(horizon: int, bucket: str, records: list[SignalRecord]) -> StatRow:
    values = [record.returns[horizon] for record in records]
    returns = np.array([value for value in values if value is not None], dtype=float)
    censored = sum(1 for value in values if value is None)

    if returns.size == 0:
        return StatRow(horizon, bucket, 0, censored, None, None, None, None, None, None, None, None)

    return StatRow(
        horizon=horizon,
        score_bucket=bucket,
        count=int(returns.size),
        censored_count=censored,
        win_rate=float((returns > 0).mean()),
        mean=float(returns.mean()),
        median=float(np.median(returns)),
        std=float(returns.std(ddof=0)),
        p25=float(np.percentile(returns, 25)),
        p75=float(np.percentile(returns, 75)),
        min=float(returns.min()),
        max=float(returns.max()),
    )


def aggregate(
    records: list[SignalRecord],
    *,
    horizons: tuple[int, ...] = HORIZONS,
    buckets: tuple[str, ...] = BUCKETS,
) -> list[StatRow]:
    named = {b for b in buckets if b != "ALL"}
    rows: list[StatRow] = []
    for horizon in horizons:
        for bucket in buckets:
            if bucket == "ALL":
                bucket_records = [r for r in records if r.score_bucket in named]
            else:
                bucket_records = [r for r in records if r.score_bucket == bucket]
            rows.append(_stat_row(horizon, bucket, bucket_records))
    return rows
