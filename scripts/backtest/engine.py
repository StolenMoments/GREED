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
    entry_date: date
    entry_price: float
    returns: dict[int, float | None] = field(default_factory=dict)


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
) -> list[StatRow]:
    rows: list[StatRow] = []
    for horizon in horizons:
        for bucket in BUCKETS:
            bucket_records = records if bucket == "ALL" else [
                record for record in records if record.score_bucket == bucket
            ]
            rows.append(_stat_row(horizon, bucket, bucket_records))
    return rows
