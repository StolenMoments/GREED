from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations
from statistics import median
from typing import Any, Callable

import numpy as np
import pandas as pd

from scripts.backtest.data import load_daily_ohlcv, load_weekly_ohlcv, valid_daily_ohlcv
from scripts.backtest.universe import load_active_universe
from weekly_indicators import add_all_indicators, append_future_cloud


DAILY_RALLY_STRATEGY_KIND = "daily_20d_40pct_rally"
RALLY_HORIZON_DAYS = 20
RALLY_THRESHOLD = 0.40
FORWARD_RETURN_DAYS = (20, 40, 60, 120)
MIN_DAILY_HISTORY = 180 + 120

COMPOSITE_SCORE_HORIZON = 20
STABILITY_MULTIPLIERS = {"stable": 1.0, "fragile": 0.6, "insufficient": 0.4}
STABILITY_DEFAULT_MULTIPLIER = 0.4
BREADTH_BONUS_PER_RULE = 0.05
BREADTH_BONUS_MAX_RULES = 4

logger = logging.getLogger(__name__)

DAILY_FEATURE_COLUMNS = (
    "ret_1d",
    "ret_5d",
    "ret_20d",
    "ret_60d",
    "volume_ratio_20d",
    "trading_value_ratio_20d",
    "range_pct",
    "close_to_20d_high",
    "close_to_60d_high",
    "close_to_20d_low",
    "ma5_gt_ma20",
    "ma20_gt_ma60",
    "ma60_up",
    "rsi14",
    "atr_pct_14",
)

WEEKLY_FEATURE_COLUMNS = (
    "weekly_close_gt_ma20",
    "weekly_ma5_gt_ma20",
    "weekly_volume_ratio_20w",
    "weekly_cloud_position",
    "weekly_span2_breakout_recent_4w",
)


@dataclass(slots=True)
class DailyRallySample:
    ticker: str
    name: str
    signal_date: date
    close_price: float
    label: int
    forward_returns: dict[int, float | None] = field(default_factory=dict)
    features: dict[str, bool | int | float | str | None] = field(default_factory=dict)


@dataclass(slots=True)
class DailyRallyRule:
    rule_key: str
    rule_label: str
    support: int
    positives: int
    total_matches: int
    precision: float
    base_rate: float
    lift: float
    score: float


@dataclass(slots=True)
class DailyRallyReturnStat:
    horizon: int
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
class DailyRallyPatternStat:
    pattern_key: str
    pattern_label: str
    support: int
    positives: int
    total_matches: int
    precision: float
    base_rate: float
    lift: float
    score: float
    return_stats: dict[int, DailyRallyReturnStat] = field(default_factory=dict)


@dataclass(slots=True)
class DailyRallyYearValidation:
    year: int
    total: int
    positives: int
    base_rate: float
    positive_forward_return_120d_mean: float | None
    censored_120d_count: int
    partial: bool


@dataclass(slots=True)
class DailyRallyTickerConcentration:
    ticker: str
    name: str
    total_count: int
    positive_count: int
    positive_share: float


@dataclass(slots=True)
class DailyRallyPatternStability:
    pattern_key: str
    pattern_label: str
    total_matches: int
    positives: int
    full_period_lift: float
    test_window_count: int
    median_train_lift: float | None
    median_test_lift: float | None
    test_lift_gt_1_ratio: float | None
    classification: str


@dataclass(slots=True)
class DailyRallyWalkForwardWindow:
    train_years: list[int]
    test_year: int
    pattern_key: str | None
    pattern_label: str | None
    train_support: int
    train_total_matches: int
    train_precision: float | None
    train_base_rate: float | None
    train_lift: float | None
    test_matches: int
    test_positives: int
    test_precision: float | None
    test_base_rate: float | None
    test_lift: float | None
    classification: str


@dataclass(slots=True)
class DailyRallyValidationSummary:
    summary: dict[str, Any]
    year_breakdown: list[DailyRallyYearValidation]
    ticker_concentration: list[DailyRallyTickerConcentration]
    pattern_stability: list[DailyRallyPatternStability]
    walk_forward_windows: list[DailyRallyWalkForwardWindow]
    warnings: list[str]


@dataclass(slots=True)
class DailyRallyRuleScoreBreakdown:
    rule_key: str
    rule_label: str
    rule_composite: float
    rule_quality: float
    stability_multiplier: float
    stability_classification: str
    expected_return: float
    win_rate_20d: float | None
    median_return_20d: float | None


@dataclass(slots=True)
class DailyRallyCandidate:
    ticker: str
    name: str
    signal_date: date
    close_price: float
    matched_rules: list[str] = field(default_factory=list)
    matched_rule_count: int = 0
    max_rule_score: float | None = None
    mean_rule_score: float | None = None
    features: dict[str, bool | int | float | str | None] = field(default_factory=dict)
    composite_score: float | None = None
    best_rule_key: str | None = None
    rule_quality_score: float | None = None
    stability_score: float | None = None
    stability_classification: str | None = None
    expected_return_score: float | None = None
    expected_win_rate_20d: float | None = None
    expected_median_return_20d: float | None = None
    rule_breakdowns: list[DailyRallyRuleScoreBreakdown] = field(default_factory=list)


@dataclass(slots=True)
class DailyRallyBacktestResult:
    samples: list[DailyRallySample]
    rules: list[DailyRallyRule]
    current_candidates: list[DailyRallyCandidate]
    ticker_count: int
    data_start: date | None
    data_end: date | None
    pattern_stats: list[DailyRallyPatternStat] = field(default_factory=list)
    validation: DailyRallyValidationSummary | None = None


@dataclass(frozen=True, slots=True)
class _Predicate:
    key: str
    label: str
    matcher: Callable[[DailyRallySample], bool]
    features: tuple[str, ...]


def _to_date(value: Any) -> date:
    return pd.to_datetime(value).date()


def _f(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _clean_value(value: Any) -> bool | int | float | str | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value)
    if isinstance(value, date):
        return value
    return str(value)


def _forward_return(df: pd.DataFrame, i: int, horizon: int) -> float | None:
    if i + horizon >= len(df):
        return None
    base = _f(df["close"].iloc[i])
    target = _f(df["close"].iloc[i + horizon])
    if base is None or target is None or base <= 0:
        return None
    return target / base - 1


def label_daily_rallies(
    df: pd.DataFrame,
    *,
    ticker: str = "",
    name: str = "",
) -> list[DailyRallySample]:
    price = valid_daily_ohlcv(df).sort_index()
    samples: list[DailyRallySample] = []
    last_positive_i: int | None = None

    for i in range(0, max(len(price) - RALLY_HORIZON_DAYS, 0)):
        rally_return = _forward_return(price, i, RALLY_HORIZON_DAYS)
        if rally_return is None:
            continue
        label = int(rally_return >= RALLY_THRESHOLD)
        if label and last_positive_i is not None and i - last_positive_i <= RALLY_HORIZON_DAYS:
            continue
        if label:
            last_positive_i = i

        close = _f(price["close"].iloc[i])
        if close is None:
            continue
        samples.append(
            DailyRallySample(
                ticker=ticker,
                name=name,
                signal_date=_to_date(price.index[i]),
                close_price=close,
                label=label,
                forward_returns={
                    horizon: _forward_return(price, i, horizon) for horizon in FORWARD_RETURN_DAYS
                },
            )
        )

    return samples


def _rsi14(close: pd.Series) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = losses.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    relative_strength = avg_gain / avg_loss.where(avg_loss != 0)
    rsi = 100 - (100 / (1 + relative_strength))
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100)
    rsi = rsi.mask((avg_loss == 0) & (avg_gain == 0), 50)
    return rsi


def _atr_pct_14(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(14, min_periods=14).mean()
    return atr / df["close"].where(df["close"] != 0)


def build_daily_features(df: pd.DataFrame) -> pd.DataFrame:
    price = valid_daily_ohlcv(df).sort_index().copy()
    features = pd.DataFrame(index=price.index)
    close = price["close"]
    volume = price["volume"]
    trading_value = price["trading_value"]

    features["ret_1d"] = close.pct_change(1)
    features["ret_5d"] = close.pct_change(5)
    features["ret_20d"] = close.pct_change(20)
    features["ret_60d"] = close.pct_change(60)
    features["volume_ratio_20d"] = volume / volume.rolling(20, min_periods=20).mean().where(
        lambda values: values != 0
    )
    features["trading_value_ratio_20d"] = trading_value / trading_value.rolling(
        20, min_periods=20
    ).mean().where(lambda values: values != 0)
    features["range_pct"] = (price["high"] - price["low"]) / close.where(close != 0)

    high20 = price["high"].rolling(20, min_periods=20).max()
    high60 = price["high"].rolling(60, min_periods=60).max()
    low20 = price["low"].rolling(20, min_periods=20).min()
    features["close_to_20d_high"] = close / high20.where(high20 != 0) - 1
    features["close_to_60d_high"] = close / high60.where(high60 != 0) - 1
    features["close_to_20d_low"] = close / low20.where(low20 != 0) - 1

    ma5 = close.rolling(5, min_periods=5).mean()
    ma20 = close.rolling(20, min_periods=20).mean()
    ma60 = close.rolling(60, min_periods=60).mean()
    features["ma5_gt_ma20"] = pd.Series(ma5 > ma20, index=price.index, dtype=object)
    features["ma20_gt_ma60"] = pd.Series(ma20 > ma60, index=price.index, dtype=object)
    features["ma60_up"] = pd.Series(ma60 > ma60.shift(1), index=price.index, dtype=object)
    features.loc[ma5.isna() | ma20.isna(), "ma5_gt_ma20"] = np.nan
    features.loc[ma20.isna() | ma60.isna(), "ma20_gt_ma60"] = np.nan
    features.loc[ma60.isna() | ma60.shift(1).isna(), "ma60_up"] = np.nan

    features["rsi14"] = _rsi14(close)
    features["atr_pct_14"] = _atr_pct_14(price)
    return features


def _sample_date_index(feature_df: pd.DataFrame) -> dict[date, pd.Timestamp]:
    return {pd.to_datetime(index).date(): index for index in feature_df.index}


def _row_has_required_values(row: pd.Series, required: tuple[str, ...]) -> bool:
    return all(column in row and not pd.isna(row[column]) for column in required)


def attach_daily_features(
    samples: list[DailyRallySample],
    feature_df: pd.DataFrame,
) -> list[DailyRallySample]:
    by_date = _sample_date_index(feature_df)
    attached: list[DailyRallySample] = []
    for sample in samples:
        index = by_date.get(sample.signal_date)
        if index is None:
            continue
        row = feature_df.loc[index]
        if not _row_has_required_values(row, DAILY_FEATURE_COLUMNS):
            continue
        sample.features.update({column: _clean_value(row[column]) for column in DAILY_FEATURE_COLUMNS})
        attached.append(sample)
    return attached


def build_weekly_asof_features(daily_df: pd.DataFrame, weekly_df: pd.DataFrame) -> pd.DataFrame:
    daily = valid_daily_ohlcv(daily_df).sort_index()
    result = pd.DataFrame(index=daily.index)
    if daily.empty or weekly_df.empty:
        return result

    weekly = weekly_df.sort_index().copy()
    weekly_indicators = add_all_indicators(weekly.copy())
    if len(weekly_indicators) >= 26:
        weekly_indicators = append_future_cloud(weekly_indicators)
    real_weekly = weekly_indicators[weekly_indicators["close"].notna()].copy()
    if real_weekly.empty:
        return result

    ma5 = real_weekly["close"].rolling(5, min_periods=5).mean()
    span2_breakout = (
        (real_weekly["close"].shift(1) <= real_weekly["ichi_lead2"].shift(1))
        & (real_weekly["close"] > real_weekly["ichi_lead2"])
    )
    real_weekly["weekly_source_date"] = [_to_date(index) for index in real_weekly.index]
    real_weekly["weekly_close_gt_ma20"] = real_weekly["close"] > real_weekly["ma20"]
    real_weekly["weekly_ma5_gt_ma20"] = ma5 > real_weekly["ma20"]
    real_weekly["weekly_volume_ratio_20w"] = real_weekly["volume_ratio_20"]
    real_weekly["weekly_cloud_position"] = np.select(
        [
            real_weekly["close"] > real_weekly["cloud_top"],
            real_weekly["close"] < real_weekly["cloud_bottom"],
        ],
        ["above_cloud", "below_cloud"],
        default="inside_cloud",
    )
    real_weekly["weekly_cloud_position"] = pd.Series(
        real_weekly["weekly_cloud_position"], index=real_weekly.index
    ).where(real_weekly[["cloud_top", "cloud_bottom"]].notna().all(axis=1))
    real_weekly["weekly_span2_breakout_recent_4w"] = (
        span2_breakout.rolling(4, min_periods=1).max().astype(bool)
    )

    asof_columns = ("weekly_source_date", *WEEKLY_FEATURE_COLUMNS)
    weekly_dates = list(real_weekly.index)
    for daily_index in daily.index:
        candidates = [weekly_index for weekly_index in weekly_dates if weekly_index < daily_index]
        if not candidates:
            continue
        source_index = candidates[-1]
        for column in asof_columns:
            result.loc[daily_index, column] = real_weekly.loc[source_index, column]
    return result


def attach_weekly_features(
    samples: list[DailyRallySample],
    weekly_feature_df: pd.DataFrame,
) -> list[DailyRallySample]:
    if weekly_feature_df.empty:
        return samples
    by_date = _sample_date_index(weekly_feature_df)
    attached: list[DailyRallySample] = []
    for sample in samples:
        index = by_date.get(sample.signal_date)
        if index is None:
            continue
        row = weekly_feature_df.loc[index]
        if not _row_has_required_values(row, WEEKLY_FEATURE_COLUMNS):
            continue
        sample.features.update(
            {column: _clean_value(row[column]) for column in WEEKLY_FEATURE_COLUMNS}
        )
        attached.append(sample)
    return attached


def build_samples_for_ticker(
    ticker: str,
    name: str,
    daily_df: pd.DataFrame,
    weekly_df: pd.DataFrame | None = None,
) -> list[DailyRallySample]:
    daily = valid_daily_ohlcv(daily_df).sort_index()
    if daily.empty:
        return []

    samples = label_daily_rallies(daily, ticker=ticker, name=name)
    samples = attach_daily_features(samples, build_daily_features(daily))
    if weekly_df is not None and not weekly_df.empty:
        samples = attach_weekly_features(samples, build_weekly_asof_features(daily, weekly_df))

    daily_dates = [pd.to_datetime(index).date() for index in daily.index]
    sample_indexes = {sample.signal_date: daily_dates.index(sample.signal_date) for sample in samples}
    positive_indexes = [sample_indexes[sample.signal_date] for sample in samples if sample.label == 1]
    if not positive_indexes:
        return samples

    filtered: list[DailyRallySample] = []
    for sample in samples:
        if sample.label == 1:
            filtered.append(sample)
            continue
        i = sample_indexes[sample.signal_date]
        if any(abs(i - positive_i) <= RALLY_HORIZON_DAYS for positive_i in positive_indexes):
            continue
        filtered.append(sample)
    return filtered


def build_daily_rally_samples(
    db,
    universe: list[tuple[str, str]] | None = None,
) -> list[DailyRallySample]:
    samples, _ticker_count, _data_start, _data_end = _collect_daily_rally_samples(db, universe)
    return samples


def _collect_daily_rally_samples(
    db,
    universe: list[tuple[str, str]] | None = None,
) -> tuple[list[DailyRallySample], int, date | None, date | None]:
    selected_universe = universe if universe is not None else load_active_universe(db)
    samples: list[DailyRallySample] = []
    processed = 0
    data_start: date | None = None
    data_end: date | None = None

    for ticker, name in selected_universe:
        daily = load_daily_ohlcv(db, ticker, fetch_missing=False)
        if daily.empty or len(daily) < MIN_DAILY_HISTORY:
            continue
        weekly = load_weekly_ohlcv(db, ticker)
        ticker_samples = build_samples_for_ticker(
            ticker,
            name,
            daily,
            weekly if weekly is not None and not weekly.empty else None,
        )
        samples.extend(ticker_samples)
        processed += 1
        first = pd.to_datetime(daily.index.min()).date()
        last = pd.to_datetime(daily.index.max()).date()
        data_start = first if data_start is None else min(data_start, first)
        data_end = last if data_end is None else max(data_end, last)

    return samples, processed, data_start, data_end


def _threshold_predicate(feature: str, threshold: float) -> _Predicate:
    key = f"{feature}>={threshold:.2f}"
    label = f"{feature} >= {threshold:.2f}"
    return _Predicate(
        key=key,
        label=label,
        matcher=lambda sample, feature=feature, threshold=threshold: (
            (value := sample.features.get(feature)) is not None
            and not isinstance(value, str)
            and float(value) >= threshold
        ),
        features=(feature,),
    )


def _equality_predicate(feature: str, expected: bool | str) -> _Predicate:
    key = f"{feature}=={expected}"
    label = f"{feature} == {expected}"
    return _Predicate(
        key=key,
        label=label,
        matcher=lambda sample, feature=feature, expected=expected: sample.features.get(feature)
        == expected,
        features=(feature,),
    )


def build_rule_candidates(samples: list[DailyRallySample]) -> list[_Predicate]:
    del samples
    return [
        _threshold_predicate("ret_1d", 0.03),
        _threshold_predicate("ret_1d", 0.05),
        _threshold_predicate("ret_1d", 0.08),
        _threshold_predicate("ret_5d", 0.08),
        _threshold_predicate("ret_5d", 0.12),
        _threshold_predicate("ret_5d", 0.18),
        _threshold_predicate("ret_20d", 0.10),
        _threshold_predicate("ret_20d", 0.20),
        _threshold_predicate("ret_20d", 0.30),
        _threshold_predicate("ret_60d", 0.20),
        _threshold_predicate("ret_60d", 0.30),
        _threshold_predicate("ret_60d", 0.50),
        _threshold_predicate("volume_ratio_20d", 1.50),
        _threshold_predicate("volume_ratio_20d", 2.00),
        _threshold_predicate("volume_ratio_20d", 3.00),
        _threshold_predicate("volume_ratio_20d", 5.00),
        _threshold_predicate("trading_value_ratio_20d", 1.50),
        _threshold_predicate("trading_value_ratio_20d", 2.00),
        _threshold_predicate("trading_value_ratio_20d", 3.00),
        _threshold_predicate("trading_value_ratio_20d", 5.00),
        _threshold_predicate("close_to_20d_high", -0.10),
        _threshold_predicate("close_to_20d_high", -0.05),
        _threshold_predicate("close_to_20d_high", -0.03),
        _threshold_predicate("close_to_60d_high", -0.05),
        _threshold_predicate("close_to_20d_low", 0.10),
        _threshold_predicate("close_to_20d_low", 0.20),
        _threshold_predicate("close_to_20d_low", 0.30),
        _threshold_predicate("range_pct", 0.05),
        _threshold_predicate("range_pct", 0.08),
        _threshold_predicate("range_pct", 0.12),
        _threshold_predicate("rsi14", 60.00),
        _threshold_predicate("rsi14", 70.00),
        _threshold_predicate("atr_pct_14", 0.03),
        _threshold_predicate("atr_pct_14", 0.04),
        _threshold_predicate("atr_pct_14", 0.06),
        _equality_predicate("ma5_gt_ma20", True),
        _equality_predicate("ma20_gt_ma60", True),
        _equality_predicate("ma60_up", True),
        _equality_predicate("weekly_close_gt_ma20", True),
        _equality_predicate("weekly_ma5_gt_ma20", True),
        _equality_predicate("weekly_cloud_position", "above_cloud"),
        _equality_predicate("weekly_span2_breakout_recent_4w", True),
    ]


def predicate_matches(sample: DailyRallySample, predicate: _Predicate | DailyRallyRule) -> bool:
    if isinstance(predicate, DailyRallyRule):
        predicates = {candidate.key: candidate for candidate in build_rule_candidates([])}
        return all(
            predicates[key].matcher(sample)
            for key in predicate.rule_key.split("&")
            if key in predicates
        ) and all(key in predicates for key in predicate.rule_key.split("&"))
    return predicate.matcher(sample)


def _can_combine(predicates: tuple[_Predicate, ...]) -> bool:
    features = [feature for predicate in predicates for feature in predicate.features]
    return len(features) == len(set(features))


def _compound_predicate(predicates: tuple[_Predicate, ...]) -> _Predicate:
    return _Predicate(
        key="&".join(predicate.key for predicate in predicates),
        label=" AND ".join(predicate.label for predicate in predicates),
        matcher=lambda sample, predicates=predicates: all(
            predicate.matcher(sample) for predicate in predicates
        ),
        features=tuple(feature for predicate in predicates for feature in predicate.features),
    )


def _predicate_masks(
    samples: list[DailyRallySample],
    predicates: list[_Predicate],
) -> dict[str, np.ndarray]:
    return {
        predicate.key: np.array([predicate.matcher(sample) for sample in samples], dtype=bool)
        for predicate in predicates
    }


def _label_mask(samples: list[DailyRallySample]) -> np.ndarray:
    return np.array([sample.label == 1 for sample in samples], dtype=bool)


def _rule_from_predicate(
    samples: list[DailyRallySample],
    predicate: _Predicate,
    base_rate: float,
    *,
    min_support: int,
    min_precision: float,
    min_total_matches: int = 1,
    min_lift: float = 0.0,
) -> DailyRallyRule | None:
    matches = [sample for sample in samples if predicate.matcher(sample)]
    total_matches = len(matches)
    if total_matches < min_total_matches:
        return None
    support = sum(1 for sample in matches if sample.label == 1)
    precision = support / total_matches
    lift = precision / base_rate if base_rate > 0 else 0
    if support < min_support or precision < min_precision or lift < min_lift:
        return None
    score = support * max(lift - 1, 0) * precision
    return DailyRallyRule(
        rule_key=predicate.key,
        rule_label=predicate.label,
        support=support,
        positives=support,
        total_matches=total_matches,
        precision=precision,
        base_rate=base_rate,
        lift=lift,
        score=score,
    )


def _rule_from_mask(
    predicate: _Predicate,
    mask: np.ndarray,
    label_mask: np.ndarray,
    base_rate: float,
    *,
    min_support: int,
    min_precision: float,
    min_total_matches: int,
    min_lift: float,
) -> DailyRallyRule | None:
    total_matches = int(mask.sum())
    if total_matches < min_total_matches:
        return None
    support = int((mask & label_mask).sum())
    precision = support / total_matches
    lift = precision / base_rate if base_rate > 0 else 0.0
    if support < min_support or precision < min_precision or lift < min_lift:
        return None
    score = support * max(lift - 1, 0) * precision
    return DailyRallyRule(
        rule_key=predicate.key,
        rule_label=predicate.label,
        support=support,
        positives=support,
        total_matches=total_matches,
        precision=precision,
        base_rate=base_rate,
        lift=lift,
        score=score,
    )


def _matched_samples_from_mask(
    samples: list[DailyRallySample],
    mask: np.ndarray,
) -> list[DailyRallySample]:
    return [sample for sample, matched in zip(samples, mask, strict=True) if matched]


def _iter_compound_predicates(
    predicates: list[_Predicate],
    *,
    max_width: int,
):
    for width in range(1, max_width + 1):
        for predicate_group in combinations(predicates, width):
            if _can_combine(predicate_group):
                yield _compound_predicate(predicate_group)


def _return_stat(horizon: int, samples: list[DailyRallySample]) -> DailyRallyReturnStat:
    values = [sample.forward_returns.get(horizon) for sample in samples]
    returns = np.array([value for value in values if value is not None], dtype=float)
    censored = sum(1 for value in values if value is None)

    if returns.size == 0:
        return DailyRallyReturnStat(
            horizon=horizon,
            count=0,
            censored_count=censored,
            win_rate=None,
            mean=None,
            median=None,
            std=None,
            p25=None,
            p75=None,
            min=None,
            max=None,
        )

    return DailyRallyReturnStat(
        horizon=horizon,
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


def build_pattern_stats(samples: list[DailyRallySample]) -> list[DailyRallyPatternStat]:
    if not samples:
        return []

    positive_count = sum(1 for sample in samples if sample.label == 1)
    base_rate = positive_count / len(samples)
    stats: list[DailyRallyPatternStat] = []
    predicates = build_rule_candidates(samples)
    masks = _predicate_masks(samples, predicates)
    label_mask = _label_mask(samples)

    for predicate in _iter_compound_predicates(predicates, max_width=3):
        predicate_masks = [masks[key] for key in predicate.key.split("&")]
        mask = np.logical_and.reduce(predicate_masks)
        total_matches = int(mask.sum())
        if total_matches == 0:
            continue
        support = int((mask & label_mask).sum())
        precision = support / total_matches
        lift = precision / base_rate if base_rate > 0 else 0
        score = support * max(lift - 1, 0) * precision
        matches = _matched_samples_from_mask(samples, mask)
        stats.append(
            DailyRallyPatternStat(
                pattern_key=predicate.key,
                pattern_label=predicate.label,
                support=support,
                positives=support,
                total_matches=total_matches,
                precision=precision,
                base_rate=base_rate,
                lift=lift,
                score=score,
                return_stats={
                    horizon: _return_stat(horizon, matches) for horizon in FORWARD_RETURN_DAYS
                },
            )
        )

    return sorted(
        stats,
        key=lambda stat: (-stat.score, -stat.precision, -stat.support, stat.pattern_key),
    )


def _base_rate(samples: list[DailyRallySample]) -> float:
    return (sum(1 for sample in samples if sample.label == 1) / len(samples)) if samples else 0.0


def _mean(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


def _pattern_metrics(
    samples: list[DailyRallySample],
    predicate: _Predicate,
) -> dict[str, float | int | None]:
    matches = [sample for sample in samples if predicate.matcher(sample)]
    positives = sum(1 for sample in matches if sample.label == 1)
    precision = positives / len(matches) if matches else None
    base_rate = _base_rate(samples)
    lift = (precision / base_rate) if precision is not None and base_rate > 0 else None
    return {
        "total_matches": len(matches),
        "positives": positives,
        "precision": precision,
        "base_rate": base_rate,
        "lift": lift,
    }


def _validation_classification(
    *,
    full_period_lift: float,
    test_window_count: int,
    median_test_lift: float | None,
    test_lift_gt_1_ratio: float | None,
) -> str:
    if test_window_count < 5 or median_test_lift is None or test_lift_gt_1_ratio is None:
        return "insufficient"
    if median_test_lift >= 1.2 and test_lift_gt_1_ratio >= 0.6:
        return "stable"
    if full_period_lift > 1:
        return "fragile"
    return "insufficient"


def _year_breakdown(samples: list[DailyRallySample]) -> list[DailyRallyYearValidation]:
    items: list[DailyRallyYearValidation] = []
    for year in sorted({sample.signal_date.year for sample in samples}):
        year_samples = [sample for sample in samples if sample.signal_date.year == year]
        positives = [sample for sample in year_samples if sample.label == 1]
        positive_120d = [
            float(value)
            for sample in positives
            if (value := sample.forward_returns.get(120)) is not None
        ]
        censored_120d = sum(1 for sample in year_samples if sample.forward_returns.get(120) is None)
        items.append(
            DailyRallyYearValidation(
                year=year,
                total=len(year_samples),
                positives=len(positives),
                base_rate=_base_rate(year_samples),
                positive_forward_return_120d_mean=_mean(positive_120d),
                censored_120d_count=censored_120d,
                partial=censored_120d > 0,
            )
        )
    return items


def _ticker_concentration(samples: list[DailyRallySample]) -> list[DailyRallyTickerConcentration]:
    positive_total = sum(1 for sample in samples if sample.label == 1)
    items: list[DailyRallyTickerConcentration] = []
    for ticker in sorted({sample.ticker for sample in samples}):
        ticker_samples = [sample for sample in samples if sample.ticker == ticker]
        positive_count = sum(1 for sample in ticker_samples if sample.label == 1)
        if positive_count == 0:
            continue
        first = ticker_samples[0]
        items.append(
            DailyRallyTickerConcentration(
                ticker=ticker,
                name=first.name,
                total_count=len(ticker_samples),
                positive_count=positive_count,
                positive_share=(positive_count / positive_total) if positive_total else 0.0,
            )
        )
    return sorted(
        items,
        key=lambda item: (-item.positive_count, -item.positive_share, item.ticker),
    )


def _complete_years(samples: list[DailyRallySample]) -> list[int]:
    return [
        item.year
        for item in _year_breakdown(samples)
        if item.total > 0 and not item.partial
    ]


def _samples_for_years(samples: list[DailyRallySample], years: set[int]) -> list[DailyRallySample]:
    return [sample for sample in samples if sample.signal_date.year in years]


def _window_classification(test_lift: float | None) -> str:
    if test_lift is None:
        return "insufficient"
    return "stable" if test_lift >= 1.2 else "fragile"


def build_walk_forward_windows(
    samples: list[DailyRallySample],
    *,
    min_train_support: int = 5,
    min_test_matches: int = 3,
) -> list[DailyRallyWalkForwardWindow]:
    years = _complete_years(samples)
    windows: list[DailyRallyWalkForwardWindow] = []
    predicates = build_rule_candidates(samples)

    for index in range(0, max(len(years) - 3, 0)):
        train_years = years[index : index + 3]
        test_year = years[index + 3]
        train_samples = _samples_for_years(samples, set(train_years))
        test_samples = _samples_for_years(samples, {test_year})
        train_base_rate = _base_rate(train_samples)
        test_base_rate = _base_rate(test_samples)

        candidates: list[tuple[_Predicate, dict[str, float | int | None], float]] = []
        for predicate in predicates:
            metrics = _pattern_metrics(train_samples, predicate)
            support = int(metrics["positives"] or 0)
            total_matches = int(metrics["total_matches"] or 0)
            precision = metrics["precision"]
            lift = metrics["lift"]
            if support < min_train_support or total_matches == 0 or precision is None or lift is None:
                continue
            score = support * max(float(lift) - 1, 0) * float(precision)
            candidates.append((predicate, metrics, score))

        if not candidates:
            windows.append(
                DailyRallyWalkForwardWindow(
                    train_years=train_years,
                    test_year=test_year,
                    pattern_key=None,
                    pattern_label=None,
                    train_support=0,
                    train_total_matches=0,
                    train_precision=None,
                    train_base_rate=train_base_rate,
                    train_lift=None,
                    test_matches=0,
                    test_positives=0,
                    test_precision=None,
                    test_base_rate=test_base_rate,
                    test_lift=None,
                    classification="insufficient",
                )
            )
            continue

        predicate, train_metrics, _score = sorted(
            candidates,
            key=lambda item: (
                -item[2],
                -(float(item[1]["precision"] or 0)),
                -(int(item[1]["positives"] or 0)),
                item[0].key,
            ),
        )[0]
        test_metrics = _pattern_metrics(test_samples, predicate)
        test_matches = int(test_metrics["total_matches"] or 0)
        test_lift = test_metrics["lift"] if test_matches >= min_test_matches else None
        windows.append(
            DailyRallyWalkForwardWindow(
                train_years=train_years,
                test_year=test_year,
                pattern_key=predicate.key,
                pattern_label=predicate.label,
                train_support=int(train_metrics["positives"] or 0),
                train_total_matches=int(train_metrics["total_matches"] or 0),
                train_precision=train_metrics["precision"],
                train_base_rate=train_metrics["base_rate"],
                train_lift=train_metrics["lift"],
                test_matches=test_matches,
                test_positives=int(test_metrics["positives"] or 0),
                test_precision=test_metrics["precision"] if test_matches >= min_test_matches else None,
                test_base_rate=test_metrics["base_rate"],
                test_lift=test_lift,
                classification=_window_classification(test_lift),
            )
        )
    return windows


def _pattern_stability(
    samples: list[DailyRallySample],
    *,
    min_train_support: int,
    min_test_matches: int,
) -> list[DailyRallyPatternStability]:
    years = _complete_years(samples)
    complete_samples = _samples_for_years(samples, set(years))
    predicates = build_rule_candidates(complete_samples)
    items: list[DailyRallyPatternStability] = []

    for predicate in predicates:
        full_metrics = _pattern_metrics(complete_samples, predicate)
        if int(full_metrics["total_matches"] or 0) == 0:
            continue

        train_lifts: list[float] = []
        test_lifts: list[float] = []
        for index in range(0, max(len(years) - 3, 0)):
            train_years = set(years[index : index + 3])
            test_year = years[index + 3]
            train_samples = _samples_for_years(complete_samples, train_years)
            test_samples = _samples_for_years(complete_samples, {test_year})
            train_metrics = _pattern_metrics(train_samples, predicate)
            test_metrics = _pattern_metrics(test_samples, predicate)
            if int(train_metrics["positives"] or 0) < min_train_support:
                continue
            if int(test_metrics["total_matches"] or 0) < min_test_matches:
                continue
            if train_metrics["lift"] is not None:
                train_lifts.append(float(train_metrics["lift"]))
            if test_metrics["lift"] is not None:
                test_lifts.append(float(test_metrics["lift"]))

        median_train_lift = float(median(train_lifts)) if train_lifts else None
        median_test_lift = float(median(test_lifts)) if test_lifts else None
        test_lift_gt_1_ratio = (
            sum(1 for lift in test_lifts if lift > 1) / len(test_lifts)
            if test_lifts
            else None
        )
        full_period_lift = float(full_metrics["lift"] or 0.0)
        items.append(
            DailyRallyPatternStability(
                pattern_key=predicate.key,
                pattern_label=predicate.label,
                total_matches=int(full_metrics["total_matches"] or 0),
                positives=int(full_metrics["positives"] or 0),
                full_period_lift=full_period_lift,
                test_window_count=len(test_lifts),
                median_train_lift=median_train_lift,
                median_test_lift=median_test_lift,
                test_lift_gt_1_ratio=test_lift_gt_1_ratio,
                classification=_validation_classification(
                    full_period_lift=full_period_lift,
                    test_window_count=len(test_lifts),
                    median_test_lift=median_test_lift,
                    test_lift_gt_1_ratio=test_lift_gt_1_ratio,
                ),
            )
        )

    return sorted(
        items,
        key=lambda item: (
            {"stable": 0, "fragile": 1, "insufficient": 2}.get(item.classification, 3),
            -(item.median_test_lift or 0),
            -item.full_period_lift,
            item.pattern_key,
        ),
    )


def build_daily_rally_validation(
    samples: list[DailyRallySample],
    *,
    min_train_support: int = 5,
    min_test_matches: int = 3,
) -> DailyRallyValidationSummary:
    years = _year_breakdown(samples)
    partial_years = [item.year for item in years if item.partial]
    complete_years = [item.year for item in years if not item.partial]
    warnings = [
        f"{year} has censored 120d returns and is excluded from stability checks."
        for year in partial_years
    ]
    walk_forward_windows = build_walk_forward_windows(
        samples,
        min_train_support=min_train_support,
        min_test_matches=min_test_matches,
    )
    pattern_stability = _pattern_stability(
        samples,
        min_train_support=min_train_support,
        min_test_matches=min_test_matches,
    )
    median_test_lifts = [
        item.median_test_lift
        for item in pattern_stability
        if item.median_test_lift is not None
    ]
    ticker_concentration = _ticker_concentration(samples)

    return DailyRallyValidationSummary(
        summary={
            "sample_count": len(samples),
            "positive_count": sum(1 for sample in samples if sample.label == 1),
            "complete_years": complete_years,
            "partial_years": partial_years,
            "validation_start_year": complete_years[0] if complete_years else None,
            "validation_end_year": complete_years[-1] if complete_years else None,
            "top_positive_ticker_share": ticker_concentration[0].positive_share
            if ticker_concentration
            else None,
            "walk_forward_median_lift": float(median(median_test_lifts))
            if median_test_lifts
            else None,
        },
        year_breakdown=years,
        ticker_concentration=ticker_concentration,
        pattern_stability=pattern_stability,
        walk_forward_windows=walk_forward_windows,
        warnings=warnings,
    )


def _sort_rules(rules: list[DailyRallyRule]) -> list[DailyRallyRule]:
    return sorted(rules, key=lambda rule: (-rule.score, -rule.precision, -rule.support, rule.rule_key))


def rank_rules(
    samples: list[DailyRallySample],
    *,
    min_support: int = 5,
    min_precision: float = 0.05,
    min_total_matches: int = 20,
    min_lift: float = 5.0,
    max_width: int = 3,
) -> list[DailyRallyRule]:
    if not samples:
        return []
    positive_count = sum(1 for sample in samples if sample.label == 1)
    base_rate = positive_count / len(samples) if samples else 0
    if base_rate == 0:
        return []

    predicates = build_rule_candidates(samples)
    masks = _predicate_masks(samples, predicates)
    labels = _label_mask(samples)
    rules: list[DailyRallyRule] = []

    for predicate in _iter_compound_predicates(predicates, max_width=max_width):
        predicate_masks = [masks[key] for key in predicate.key.split("&")]
        mask = np.logical_and.reduce(predicate_masks)
        rule = _rule_from_mask(
            predicate,
            mask,
            labels,
            base_rate,
            min_support=min_support,
            min_precision=min_precision,
            min_total_matches=min_total_matches,
            min_lift=min_lift,
        )
        if rule is not None:
            rules.append(rule)

    return _sort_rules(rules)


def find_current_candidates(
    samples: list[DailyRallySample],
    rules: list[DailyRallyRule],
    *,
    as_of: date | None = None,
) -> list[DailyRallyCandidate]:
    latest_by_ticker: dict[str, DailyRallySample] = {}
    for sample in samples:
        if as_of is not None and sample.signal_date > as_of:
            continue
        current = latest_by_ticker.get(sample.ticker)
        if current is None or sample.signal_date > current.signal_date:
            latest_by_ticker[sample.ticker] = sample

    candidates: list[DailyRallyCandidate] = []
    for sample in latest_by_ticker.values():
        matched = [rule for rule in rules if predicate_matches(sample, rule)]
        if not matched:
            continue
        scores = [rule.score for rule in matched]
        candidates.append(
            DailyRallyCandidate(
                ticker=sample.ticker,
                name=sample.name,
                signal_date=sample.signal_date,
                close_price=sample.close_price,
                matched_rules=[rule.rule_key for rule in matched],
                matched_rule_count=len(matched),
                max_rule_score=max(scores),
                mean_rule_score=sum(scores) / len(scores),
                features=dict(sample.features),
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (
            -(candidate.max_rule_score or 0),
            -candidate.matched_rule_count,
            candidate.ticker,
        ),
    )


def _stability_lookup(validation: DailyRallyValidationSummary | None) -> dict[str, str]:
    if validation is None:
        return {}
    return {item.pattern_key: item.classification for item in validation.pattern_stability}


def _combo_stability(rule_key: str, lookup: dict[str, str]) -> tuple[float, str]:
    worst_multiplier = 1.0
    worst_classification = "stable"
    for component_key in rule_key.split("&"):
        classification = lookup.get(component_key, "insufficient")
        multiplier = STABILITY_MULTIPLIERS.get(classification, STABILITY_DEFAULT_MULTIPLIER)
        if multiplier < worst_multiplier:
            worst_multiplier = multiplier
            worst_classification = classification
    return worst_multiplier, worst_classification


def _expected_return_score(
    stat: DailyRallyPatternStat | None,
) -> tuple[float, float | None, float | None]:
    if stat is None:
        return 0.0, None, None
    return_stat = stat.return_stats.get(COMPOSITE_SCORE_HORIZON)
    if return_stat is None or return_stat.count <= 0:
        return 0.0, None, None
    win_rate = return_stat.win_rate
    median_return = return_stat.median
    win_component = win_rate if win_rate is not None else 0.0
    median_component = (
        min(max(median_return / RALLY_THRESHOLD, 0.0), 1.0) if median_return is not None else 0.0
    )
    return 0.5 * win_component + 0.5 * median_component, win_rate, median_return


def score_candidates(
    candidates: list[DailyRallyCandidate],
    rules: list[DailyRallyRule],
    pattern_stats: list[DailyRallyPatternStat],
    validation: DailyRallyValidationSummary | None,
) -> list[DailyRallyCandidate]:
    if not candidates or not rules:
        return candidates
    rules_by_key = {rule.rule_key: rule for rule in rules}
    patterns_by_key = {stat.pattern_key: stat for stat in pattern_stats}
    stability = _stability_lookup(validation)
    max_score = max(rule.score for rule in rules)
    log_max_score = math.log1p(max_score) if max_score > 0 else 0.0

    for candidate in candidates:
        breakdowns: list[DailyRallyRuleScoreBreakdown] = []
        for rule_key in candidate.matched_rules:
            rule = rules_by_key.get(rule_key)
            if rule is None:
                continue
            rule_quality = (
                math.log1p(max(rule.score, 0.0)) / log_max_score if log_max_score > 0 else 0.0
            )
            stability_multiplier, stability_classification = _combo_stability(rule_key, stability)
            pattern_stat = patterns_by_key.get(rule_key)
            if pattern_stat is None:
                logger.warning("daily rally pattern stat missing for rule %s", rule_key)
            expected_return, win_rate, median_return = _expected_return_score(pattern_stat)
            breakdowns.append(
                DailyRallyRuleScoreBreakdown(
                    rule_key=rule_key,
                    rule_label=rule.rule_label,
                    rule_composite=100 * (0.5 * rule_quality + 0.5 * expected_return) * stability_multiplier,
                    rule_quality=rule_quality,
                    stability_multiplier=stability_multiplier,
                    stability_classification=stability_classification,
                    expected_return=expected_return,
                    win_rate_20d=win_rate,
                    median_return_20d=median_return,
                )
            )
        if not breakdowns:
            continue
        breakdowns.sort(key=lambda item: (-item.rule_composite, item.rule_key))
        best = breakdowns[0]
        breadth_bonus = 1 + BREADTH_BONUS_PER_RULE * min(
            candidate.matched_rule_count - 1, BREADTH_BONUS_MAX_RULES
        )
        candidate.composite_score = min(100.0, best.rule_composite * breadth_bonus)
        candidate.best_rule_key = best.rule_key
        candidate.rule_quality_score = best.rule_quality
        candidate.stability_score = best.stability_multiplier
        candidate.stability_classification = best.stability_classification
        candidate.expected_return_score = best.expected_return
        candidate.expected_win_rate_20d = best.win_rate_20d
        candidate.expected_median_return_20d = best.median_return_20d
        candidate.rule_breakdowns = breakdowns

    return sorted(
        candidates,
        key=lambda candidate: (
            -(candidate.composite_score or 0),
            -(candidate.max_rule_score or 0),
            candidate.ticker,
        ),
    )


def run_daily_rally_backtest(db, universe: list[tuple[str, str]] | None = None) -> DailyRallyBacktestResult:
    samples, ticker_count, data_start, data_end = _collect_daily_rally_samples(db, universe)
    pattern_stats = build_pattern_stats(samples)
    validation = build_daily_rally_validation(samples)
    rules = rank_rules(samples)
    current_candidates = score_candidates(
        find_current_candidates(samples, rules), rules, pattern_stats, validation
    )
    return DailyRallyBacktestResult(
        samples=samples,
        rules=rules,
        current_candidates=current_candidates,
        pattern_stats=pattern_stats,
        validation=validation,
        ticker_count=ticker_count,
        data_start=data_start,
        data_end=data_end,
    )
