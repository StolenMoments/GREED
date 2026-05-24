from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from backend.models import Analysis
from scripts.backtest.data import load_weekly_ohlcv
from scripts.backtest.engine import (
    HORIZONS,
    WARMUP_WEEKS,
    SignalRecord,
    StatRow,
    _f,
    _to_date,
    aggregate,
    build_combined,
)
from scripts.backtest.universe import DEFAULT_UNIVERSE_PATH, load_universe
from scripts.rule_scorer.features import Features, extract_features_asof
from scripts.rule_scorer.score import score_features


SIMILARITY_THRESHOLDS = (10, 11, 12)
SIMILARITY_BUCKETS = ("10-11", "12+", "ALL")
SIMILARITY_WEIGHTS = {
    "cloud_position": 3,
    "ma_alignment": 3,
    "trend": 2,
    "macd_hist_direction": 2,
    "rsi_bucket": 1,
    "volume_bucket": 1,
    "strict_divergence": 1,
    "future_cloud_direction": 1,
}


@dataclass(frozen=True, slots=True)
class SimilarityProfile:
    trend: str
    cloud_position: str
    ma_alignment: str
    macd_hist_direction: str
    rsi_bucket: str
    volume_bucket: str
    strict_divergence: str
    future_cloud_direction: str


@dataclass(slots=True)
class AnalysisBacktestResult:
    records: list[SignalRecord] = field(default_factory=list)
    stats: list[StatRow] = field(default_factory=list)
    ticker_count: int = 0
    data_start: date | None = None
    data_end: date | None = None
    base_score: int = 0
    base_judgment: str = ""
    base_profile: SimilarityProfile | None = None


def bucket_macd_hist(current: float | None, prev: float | None, prev2: float | None) -> str:
    if current is None or prev is None or prev2 is None:
        return "unknown"
    if current > 0 and current > prev > prev2:
        return "rising_positive"
    if current < 0 and current < prev < prev2:
        return "falling_negative"
    return "other"


def bucket_rsi(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 45:
        return "low"
    if value <= 65:
        return "mid"
    if value <= 75:
        return "high"
    return "overheated"


def bucket_volume(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 0.7:
        return "dry"
    if value < 1.0:
        return "normal"
    return "active"


def profile_from_features(features: Features) -> tuple[SimilarityProfile, int, str]:
    score = score_features(features)
    return (
        SimilarityProfile(
            trend=score.trend,
            cloud_position=score.cloud_position,
            ma_alignment=score.ma_alignment,
            macd_hist_direction=bucket_macd_hist(
                features.macd_hist,
                features.macd_hist_prev,
                features.macd_hist_prev2,
            ),
            rsi_bucket=bucket_rsi(features.rsi14),
            volume_bucket=bucket_volume(features.volume_ratio_20),
            strict_divergence=features.strict_divergence
            if features.strict_divergence in {"bullish", "bearish"}
            else "none",
            future_cloud_direction=features.future_cloud_direction or "unknown",
        ),
        score.total,
        score.judgment,
    )


def similarity_score(base: SimilarityProfile, candidate: SimilarityProfile) -> int:
    total = 0
    for field_name, weight in SIMILARITY_WEIGHTS.items():
        base_value = getattr(base, field_name)
        candidate_value = getattr(candidate, field_name)
        if base_value == "unknown" or candidate_value == "unknown":
            continue
        if base_value == candidate_value:
            total += weight
    return total


def analysis_score_bucket(score: int) -> str:
    if score >= 12:
        return "12+"
    return "10-11"


def analysis_asof_index(combined: pd.DataFrame, analysis_created_at) -> int:
    price = combined[combined["close"].notna()].reset_index(drop=True)
    if price.empty:
        raise ValueError("CSV has no price rows")

    analysis_date = pd.to_datetime(analysis_created_at).date()
    dates = pd.to_datetime(price["date"]).dt.date
    candidates = [idx for idx, value in enumerate(dates) if value <= analysis_date]
    if not candidates:
        raise ValueError("No weekly row exists on or before analysis date")
    return candidates[-1]


def run_similarity_ticker(
    combined: pd.DataFrame,
    *,
    base_profile: SimilarityProfile,
    threshold: int,
    horizons: tuple[int, ...] = HORIZONS,
    warmup: int = WARMUP_WEEKS,
) -> list[SignalRecord]:
    if threshold not in SIMILARITY_THRESHOLDS:
        raise ValueError(f"Unsupported similarity threshold: {threshold}")

    price = combined[combined["close"].notna()].reset_index(drop=True)
    n = len(price)
    records: list[SignalRecord] = []
    last_entry_i = n - 2

    for i in range(warmup, last_entry_i + 1):
        features = extract_features_asof(combined, i)
        candidate_profile, _candidate_score, _candidate_judgment = profile_from_features(features)
        score = similarity_score(base_profile, candidate_profile)
        if score < threshold:
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
                ticker=features.ticker,
                name=features.name,
                signal_date=_to_date(price["date"].iloc[i]),
                score=score,
                score_bucket=analysis_score_bucket(score),
                entry_date=_to_date(price["date"].iloc[i + 1]),
                entry_price=entry_price,
                returns=returns,
            )
        )

    return records


def run_analysis_similarity_backtest(
    db: Session,
    analysis: Analysis,
    *,
    threshold: int,
    warmup: int = WARMUP_WEEKS,
    universe_path=DEFAULT_UNIVERSE_PATH,
) -> AnalysisBacktestResult:
    if threshold not in SIMILARITY_THRESHOLDS:
        raise ValueError(f"Unsupported similarity threshold: {threshold}")

    base_weekly = load_weekly_ohlcv(db, analysis.ticker)
    if base_weekly.empty or len(base_weekly) <= warmup + 1:
        raise ValueError(f"Not enough weekly data for base analysis ticker: {analysis.ticker}")

    base_combined = build_combined(base_weekly, analysis.ticker, analysis.name)
    base_index = analysis_asof_index(base_combined, analysis.created_at)
    base_profile, base_score, base_judgment = profile_from_features(
        extract_features_asof(base_combined, base_index)
    )

    records: list[SignalRecord] = []
    data_start: date | None = None
    data_end: date | None = None
    processed = 0

    for code, name in load_universe(universe_path):
        weekly = load_weekly_ohlcv(db, code)
        if weekly.empty or len(weekly) <= warmup + 1:
            continue

        combined = build_combined(weekly, code, name)
        records.extend(
            run_similarity_ticker(
                combined,
                base_profile=base_profile,
                threshold=threshold,
                warmup=warmup,
            )
        )
        processed += 1
        first = weekly.index.min().date()
        last = weekly.index.max().date()
        data_start = first if data_start is None else min(data_start, first)
        data_end = last if data_end is None else max(data_end, last)

    return AnalysisBacktestResult(
        records=records,
        stats=aggregate(records, buckets=SIMILARITY_BUCKETS),
        ticker_count=processed,
        data_start=data_start,
        data_end=data_end,
        base_score=base_score,
        base_judgment=base_judgment,
        base_profile=base_profile,
    )
