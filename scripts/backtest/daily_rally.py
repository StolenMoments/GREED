from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from itertools import combinations
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


@dataclass(slots=True)
class DailyRallyBacktestResult:
    samples: list[DailyRallySample]
    rules: list[DailyRallyRule]
    current_candidates: list[DailyRallyCandidate]
    ticker_count: int
    data_start: date | None
    data_end: date | None
    pattern_stats: list[DailyRallyPatternStat] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _Predicate:
    key: str
    label: str
    matcher: Callable[[DailyRallySample], bool]


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
    )


def _equality_predicate(feature: str, expected: bool | str) -> _Predicate:
    key = f"{feature}=={expected}"
    label = f"{feature} == {expected}"
    return _Predicate(
        key=key,
        label=label,
        matcher=lambda sample, feature=feature, expected=expected: sample.features.get(feature)
        == expected,
    )


def build_rule_candidates(samples: list[DailyRallySample]) -> list[_Predicate]:
    del samples
    return [
        _threshold_predicate("ret_20d", 0.10),
        _threshold_predicate("ret_20d", 0.20),
        _threshold_predicate("ret_60d", 0.30),
        _threshold_predicate("volume_ratio_20d", 2.00),
        _threshold_predicate("volume_ratio_20d", 3.00),
        _threshold_predicate("trading_value_ratio_20d", 2.00),
        _threshold_predicate("trading_value_ratio_20d", 3.00),
        _threshold_predicate("close_to_20d_high", -0.03),
        _threshold_predicate("close_to_60d_high", -0.05),
        _threshold_predicate("close_to_20d_low", 0.20),
        _threshold_predicate("range_pct", 0.08),
        _threshold_predicate("rsi14", 60.00),
        _threshold_predicate("rsi14", 70.00),
        _threshold_predicate("atr_pct_14", 0.04),
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


def _rule_from_predicate(
    samples: list[DailyRallySample],
    predicate: _Predicate,
    base_rate: float,
    *,
    min_support: int,
    min_precision: float,
) -> DailyRallyRule | None:
    matches = [sample for sample in samples if predicate.matcher(sample)]
    total_matches = len(matches)
    if total_matches == 0:
        return None
    support = sum(1 for sample in matches if sample.label == 1)
    precision = support / total_matches
    if support < min_support or precision < min_precision:
        return None
    lift = precision / base_rate if base_rate > 0 else 0
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

    for predicate in build_rule_candidates(samples):
        matches = [sample for sample in samples if predicate.matcher(sample)]
        total_matches = len(matches)
        if total_matches == 0:
            continue
        support = sum(1 for sample in matches if sample.label == 1)
        precision = support / total_matches
        lift = precision / base_rate if base_rate > 0 else 0
        score = support * max(lift - 1, 0) * precision
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


def _sort_rules(rules: list[DailyRallyRule]) -> list[DailyRallyRule]:
    return sorted(rules, key=lambda rule: (-rule.score, -rule.precision, -rule.support, rule.rule_key))


def rank_rules(
    samples: list[DailyRallySample],
    *,
    min_support: int = 5,
    min_precision: float = 0.15,
) -> list[DailyRallyRule]:
    if not samples:
        return []
    positive_count = sum(1 for sample in samples if sample.label == 1)
    base_rate = positive_count / len(samples) if samples else 0
    if base_rate == 0:
        return []

    predicates = build_rule_candidates(samples)
    single_rules = [
        rule
        for predicate in predicates
        if (
            rule := _rule_from_predicate(
                samples,
                predicate,
                base_rate,
                min_support=min_support,
                min_precision=min_precision,
            )
        )
        is not None
    ]
    ranked_singles = _sort_rules(single_rules)

    predicate_by_key = {predicate.key: predicate for predicate in predicates}
    combo_rules: list[DailyRallyRule] = []
    for left, right in combinations(ranked_singles[:30], 2):
        left_predicate = predicate_by_key[left.rule_key]
        right_predicate = predicate_by_key[right.rule_key]
        combo = _Predicate(
            key=f"{left.rule_key}&{right.rule_key}",
            label=f"{left.rule_label} AND {right.rule_label}",
            matcher=lambda sample, left_predicate=left_predicate, right_predicate=right_predicate: (
                left_predicate.matcher(sample) and right_predicate.matcher(sample)
            ),
        )
        rule = _rule_from_predicate(
            samples,
            combo,
            base_rate,
            min_support=min_support,
            min_precision=min_precision,
        )
        if rule is not None:
            combo_rules.append(rule)

    return _sort_rules([*ranked_singles, *combo_rules])


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


def run_daily_rally_backtest(db, universe: list[tuple[str, str]] | None = None) -> DailyRallyBacktestResult:
    samples, ticker_count, data_start, data_end = _collect_daily_rally_samples(db, universe)
    pattern_stats = build_pattern_stats(samples)
    rules = rank_rules(samples)
    current_candidates = find_current_candidates(samples, rules)
    return DailyRallyBacktestResult(
        samples=samples,
        rules=rules,
        current_candidates=current_candidates,
        pattern_stats=pattern_stats,
        ticker_count=ticker_count,
        data_start=data_start,
        data_end=data_end,
    )
