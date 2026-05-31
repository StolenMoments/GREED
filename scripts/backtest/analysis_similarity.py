from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from backend.models import Analysis
from scripts.backtest.data import load_daily_ohlcv, load_weekly_ohlcv, valid_daily_ohlcv
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
from scripts.backtest.universe import load_active_universe, load_universe
from scripts.rule_scorer.features import Features, extract_features_asof
from scripts.rule_scorer.score import score_features


SIMILARITY_THRESHOLDS = (10, 11, 12)
SIMILARITY_BUCKETS = ("10", "11", "12", "13", "14", "ALL")
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


@dataclass(frozen=True, slots=True)
class ContractEvent:
    entry_date: date | None
    exit_date: date | None
    exit_reason: str
    exit_price: float | None
    event_return: float | None
    days_held: int | None


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
    return str(score)


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


def _profile_with_analysis_fields(profile: SimilarityProfile, analysis: Analysis) -> SimilarityProfile:
    return replace(
        profile,
        trend=analysis.trend or profile.trend,
        cloud_position=analysis.cloud_position or profile.cloud_position,
        ma_alignment=analysis.ma_alignment or profile.ma_alignment,
    )


def _is_buy_judgment(value: str) -> bool:
    return value in {"buy", "\ub9e4\uc218", "留ㅼ닔"}


def _validate_contract_analysis(analysis: Analysis) -> None:
    if not _is_buy_judgment(analysis.judgment):
        raise ValueError("Contract backtest requires a buy analysis")
    required = {
        "entry_price": analysis.entry_price,
        "target_price": analysis.target_price,
        "stop_loss": analysis.stop_loss,
    }
    missing = [name for name, value in required.items() if value is None or value <= 0]
    if missing:
        raise ValueError(
            "Contract backtest requires positive entry_price, target_price, and stop_loss "
            f"(missing: {', '.join(missing)})"
        )


def _asof_close(daily: pd.DataFrame, asof_date: date) -> float:
    price = daily[daily["close"].notna()].copy()
    if price.empty:
        raise ValueError("No daily close data available")
    dates = pd.to_datetime(price.index).date
    candidates = price.loc[[value <= asof_date for value in dates]]
    if candidates.empty:
        raise ValueError("No daily close exists on or before analysis date")
    close = _f(candidates["close"].iloc[-1])
    if close is None or close <= 0:
        raise ValueError("Invalid as-of daily close")
    return close


def contract_event_for_candidate(
    daily: pd.DataFrame,
    *,
    signal_date: date,
    entry_price: float,
    target_price: float,
    stop_price: float,
    max_entry_days: int = 20,
    max_hold_days: int = 130,
) -> ContractEvent:
    price = valid_daily_ohlcv(daily.sort_index())
    if price.empty:
        return ContractEvent(None, None, "no_entry", None, None, None)

    dates = list(pd.to_datetime(price.index).date)
    start_idx = next((idx for idx, value in enumerate(dates) if value > signal_date), None)
    if start_idx is None:
        return ContractEvent(None, None, "no_entry", None, None, None)

    entry_idx: int | None = None
    last_entry_idx = min(len(price) - 1, start_idx + max_entry_days - 1)
    for idx in range(start_idx, last_entry_idx + 1):
        low = _f(price["low"].iloc[idx])
        high = _f(price["high"].iloc[idx])
        if low is None or high is None:
            continue
        if low <= entry_price <= high:
            entry_idx = idx
            break

    if entry_idx is None:
        return ContractEvent(None, None, "no_entry", None, None, None)

    entry_date = dates[entry_idx]
    last_hold_idx = min(len(price) - 1, entry_idx + max_hold_days)
    for idx in range(entry_idx, last_hold_idx + 1):
        low = _f(price["low"].iloc[idx])
        high = _f(price["high"].iloc[idx])
        if low is None or high is None:
            continue
        exit_date = dates[idx]
        if low <= stop_price:
            return ContractEvent(
                entry_date=entry_date,
                exit_date=exit_date,
                exit_reason="stop",
                exit_price=stop_price,
                event_return=stop_price / entry_price - 1,
                days_held=(exit_date - entry_date).days,
            )
        if high >= target_price:
            return ContractEvent(
                entry_date=entry_date,
                exit_date=exit_date,
                exit_reason="target",
                exit_price=target_price,
                event_return=target_price / entry_price - 1,
                days_held=(exit_date - entry_date).days,
            )

    exit_date = dates[last_hold_idx]
    exit_price = _f(price["close"].iloc[last_hold_idx])
    if exit_price is None:
        return ContractEvent(entry_date, exit_date, "expiry", None, None, None)
    return ContractEvent(
        entry_date=entry_date,
        exit_date=exit_date,
        exit_reason="expiry",
        exit_price=exit_price,
        event_return=exit_price / entry_price - 1,
        days_held=(exit_date - entry_date).days,
    )


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
    universe_path=None,
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

    universe = load_universe(universe_path) if universe_path is not None else load_active_universe(db)
    for code, name in universe:
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


def run_analysis_contract_backtest(
    db: Session,
    analysis: Analysis,
    *,
    threshold: int = 10,
    warmup: int = WARMUP_WEEKS,
    universe_path=None,
) -> AnalysisBacktestResult:
    if threshold not in SIMILARITY_THRESHOLDS:
        raise ValueError(f"Unsupported similarity threshold: {threshold}")
    _validate_contract_analysis(analysis)

    base_weekly = load_weekly_ohlcv(db, analysis.ticker)
    if base_weekly.empty or len(base_weekly) <= warmup + 1:
        raise ValueError(f"Not enough weekly data for base analysis ticker: {analysis.ticker}")

    base_daily = load_daily_ohlcv(db, analysis.ticker, fetch_missing=True)
    if base_daily.empty:
        raise ValueError(f"No daily data for base analysis ticker: {analysis.ticker}")

    base_combined = build_combined(base_weekly, analysis.ticker, analysis.name)
    base_index = analysis_asof_index(base_combined, analysis.created_at)
    base_signal_date = _to_date(base_combined[base_combined["close"].notna()].reset_index(drop=True)["date"].iloc[base_index])
    base_close = _asof_close(base_daily, base_signal_date)

    assert analysis.entry_price is not None
    assert analysis.target_price is not None
    assert analysis.stop_loss is not None
    entry_ratio = analysis.entry_price / base_close
    target_return = analysis.target_price / analysis.entry_price - 1
    stop_return = analysis.stop_loss / analysis.entry_price - 1

    base_profile, base_score, base_judgment = profile_from_features(
        extract_features_asof(base_combined, base_index)
    )
    base_profile = _profile_with_analysis_fields(base_profile, analysis)

    records: list[SignalRecord] = []
    data_start: date | None = None
    data_end: date | None = None
    processed = 0

    universe = load_universe(universe_path) if universe_path is not None else load_active_universe(db)
    for code, name in universe:
        weekly = load_weekly_ohlcv(db, code)
        daily = load_daily_ohlcv(db, code)
        if weekly.empty or len(weekly) <= warmup + 1 or daily.empty:
            continue

        combined = build_combined(weekly, code, name)
        candidates = run_similarity_ticker(
            combined,
            base_profile=base_profile,
            threshold=threshold,
            warmup=warmup,
        )
        for candidate in candidates:
            try:
                candidate_close = _asof_close(daily, candidate.signal_date)
            except ValueError:
                continue
            entry_price = candidate_close * entry_ratio
            target_price = entry_price * (1 + target_return)
            stop_price = entry_price * (1 + stop_return)
            event = contract_event_for_candidate(
                daily,
                signal_date=candidate.signal_date,
                entry_price=entry_price,
                target_price=target_price,
                stop_price=stop_price,
            )
            records.append(
                SignalRecord(
                    ticker=candidate.ticker,
                    name=candidate.name,
                    signal_date=candidate.signal_date,
                    score=candidate.score,
                    score_bucket=candidate.score_bucket,
                    entry_date=event.entry_date,
                    entry_price=entry_price,
                    returns={},
                    exit_date=event.exit_date,
                    exit_reason=event.exit_reason,
                    exit_price=event.exit_price,
                    event_return=event.event_return,
                    days_held=event.days_held,
                )
            )

        processed += 1
        first = daily.index.min().date()
        last = daily.index.max().date()
        data_start = first if data_start is None else min(data_start, first)
        data_end = last if data_end is None else max(data_end, last)

    return AnalysisBacktestResult(
        records=records,
        stats=[],
        ticker_count=processed,
        data_start=data_start,
        data_end=data_end,
        base_score=base_score,
        base_judgment=base_judgment,
        base_profile=base_profile,
    )


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    ticker: str
    name: str
    score: int
    current_close: float
    entry_price: float
    target_price: float
    stop_price: float
    entry_gap_pct: float


def scan_current_candidates(
    db: Session,
    analysis: Analysis,
    *,
    threshold: int = 12,
    warmup: int = WARMUP_WEEKS,
) -> tuple[list[CandidateRecord], date]:
    """KOSPI200-DB 유니버스에서 최신 주봉 기준 similarity >= threshold 종목을 반환."""
    if not (10 <= threshold <= 14):
        raise ValueError(f"threshold must be 10–14, got {threshold}")
    _validate_contract_analysis(analysis)

    base_weekly = load_weekly_ohlcv(db, analysis.ticker)
    if base_weekly.empty or len(base_weekly) <= warmup + 1:
        raise ValueError(f"Not enough weekly data for base ticker: {analysis.ticker}")

    base_daily = load_daily_ohlcv(db, analysis.ticker, fetch_missing=True)
    if base_daily.empty:
        raise ValueError(f"No daily data for base ticker: {analysis.ticker}")

    base_combined = build_combined(base_weekly, analysis.ticker, analysis.name)
    base_index = analysis_asof_index(base_combined, analysis.created_at)
    base_signal_date = _to_date(
        base_combined[base_combined["close"].notna()].reset_index(drop=True)["date"].iloc[base_index]
    )
    base_close = _asof_close(base_daily, base_signal_date)

    assert analysis.entry_price is not None
    assert analysis.target_price is not None
    assert analysis.stop_loss is not None
    entry_ratio = analysis.entry_price / base_close
    target_return = analysis.target_price / analysis.entry_price - 1
    stop_return = analysis.stop_loss / analysis.entry_price - 1

    base_profile, _, _ = profile_from_features(extract_features_asof(base_combined, base_index))
    base_profile = _profile_with_analysis_fields(base_profile, analysis)

    results: list[CandidateRecord] = []
    latest_scan_date: date | None = None

    universe = load_active_universe(db)
    for code, name in universe:
        weekly = load_weekly_ohlcv(db, code)
        if weekly.empty:
            continue
        combined = build_combined(weekly, code, name)
        price = combined[combined["close"].notna()].reset_index(drop=True)
        n = len(price)
        if n <= warmup:
            continue

        i = n - 1  # 최신 완성 주봉
        features = extract_features_asof(combined, i)
        candidate_profile, _, _ = profile_from_features(features)
        score = similarity_score(base_profile, candidate_profile)
        if score < threshold:
            continue

        current_close = _f(price["close"].iloc[i])
        if current_close is None or current_close <= 0:
            continue

        bar_date = _to_date(price["date"].iloc[i])
        if latest_scan_date is None or bar_date > latest_scan_date:
            latest_scan_date = bar_date

        ep = current_close * entry_ratio
        tp = ep * (1 + target_return)
        sp = ep * (1 + stop_return)
        gap = (ep - current_close) / current_close * 100

        results.append(CandidateRecord(
            ticker=code,
            name=name,
            score=score,
            current_close=current_close,
            entry_price=ep,
            target_price=tp,
            stop_price=sp,
            entry_gap_pct=gap,
        ))

    from datetime import date as _date_cls
    return results, latest_scan_date or _date_cls.today()
