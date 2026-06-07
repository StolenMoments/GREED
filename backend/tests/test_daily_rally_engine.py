from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from scripts.backtest import daily_rally as daily_rally_module
from scripts.backtest.daily_rally import (
    DailyRallyRule,
    DailyRallySample,
    build_daily_features,
    build_samples_for_ticker,
    build_weekly_asof_features,
    find_current_candidates,
    label_daily_rallies,
    rank_rules,
    run_daily_rally_backtest,
)


def _daily_frame(
    closes: list[float],
    *,
    start: str = "2024-01-02",
    volume: float = 1000.0,
) -> pd.DataFrame:
    index = pd.bdate_range(start, periods=len(closes))
    close = pd.Series(closes, index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": volume,
            "trading_value": close * volume,
        },
        index=index,
    )


def test_label_daily_rallies_uses_d_plus_20_close() -> None:
    closes = [100.0] * 20 + [141.0]
    samples = label_daily_rallies(_daily_frame(closes))

    first = samples[0]
    assert first.signal_date == date(2024, 1, 2)
    assert first.label == 1
    assert first.forward_returns[20] == pytest.approx(0.41)


def test_label_daily_rallies_deduplicates_positive_events_within_20_sessions() -> None:
    closes = [100.0] * 40
    closes[30] = 150.0
    closes[35] = 150.0

    samples = label_daily_rallies(_daily_frame(closes))
    positive_dates = [sample.signal_date for sample in samples if sample.label == 1]

    assert positive_dates == [pd.bdate_range("2024-01-02", periods=11)[-1].date()]


def test_daily_features_do_not_use_future_rows() -> None:
    base = [100.0 + i for i in range(80)]
    changed = base.copy()
    changed[41:] = [value * 10 for value in changed[41:]]
    d = _daily_frame(base).index[40]

    features = build_daily_features(_daily_frame(base))
    changed_features = build_daily_features(_daily_frame(changed))

    for key in ("ret_20d", "volume_ratio_20d", "ma5_gt_ma20"):
        assert changed_features.loc[d, key] == pytest.approx(features.loc[d, key])


def test_weekly_features_use_last_completed_week_only() -> None:
    daily = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [101.0, 102.0],
            "low": [99.0, 100.0],
            "close": [100.0, 101.0],
            "volume": [1000.0, 1000.0],
            "trading_value": [100000.0, 101000.0],
        },
        index=pd.to_datetime(["2024-01-03", "2024-01-08"]),
    )
    weekly = pd.DataFrame(
        {
            "open": [100.0, 200.0],
            "high": [101.0, 220.0],
            "low": [99.0, 190.0],
            "close": [100.0, 210.0],
            "volume": [1000.0, 9000.0],
            "trading_value": [100000.0, 1890000.0],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-08"]),
    )

    features = build_weekly_asof_features(daily, weekly)

    assert features.loc[pd.Timestamp("2024-01-03"), "weekly_source_date"] == date(2024, 1, 1)
    assert features.loc[pd.Timestamp("2024-01-08"), "weekly_source_date"] == date(2024, 1, 1)


def test_control_samples_exclude_positive_neighborhood() -> None:
    closes = [100.0 + i * 0.1 for i in range(340)]
    closes[220] = closes[200] * 1.5
    samples = build_samples_for_ticker("005930", "Samsung", _daily_frame(closes))

    positives = [sample for sample in samples if sample.label == 1]
    controls = [sample for sample in samples if sample.label == 0]
    positive_date = positives[0].signal_date
    all_dates = list(_daily_frame(closes).index.date)
    positive_i = all_dates.index(positive_date)
    control_indexes = {all_dates.index(sample.signal_date) for sample in controls}

    assert positives
    assert all(abs(index - positive_i) > 20 for index in control_indexes)


def test_rank_rules_computes_support_precision_lift_and_score() -> None:
    samples = [
        DailyRallySample("A", "A", date(2024, 1, 1), 100, 1, features={"ret_20d": 0.3}),
        DailyRallySample("B", "B", date(2024, 1, 1), 100, 1, features={"ret_20d": 0.25}),
        DailyRallySample("C", "C", date(2024, 1, 1), 100, 0, features={"ret_20d": 0.22}),
        DailyRallySample("D", "D", date(2024, 1, 1), 100, 0, features={"ret_20d": 0.05}),
        DailyRallySample("E", "E", date(2024, 1, 1), 100, 0, features={"ret_20d": 0.02}),
        DailyRallySample("F", "F", date(2024, 1, 1), 100, 0, features={"ret_20d": -0.01}),
    ]

    rules = rank_rules(samples, min_support=1, min_precision=0.1)
    rule = next(rule for rule in rules if rule.rule_key == "ret_20d>=0.20")

    assert rule.support == 2
    assert rule.positives == 2
    assert rule.total_matches == 3
    assert rule.base_rate == pytest.approx(2 / 6)
    assert rule.precision == pytest.approx(2 / 3)
    assert rule.lift == pytest.approx(2.0)
    assert rule.score == pytest.approx(2 * 1.0 * (2 / 3))


def test_find_current_candidates_uses_latest_sample_per_ticker() -> None:
    samples = [
        DailyRallySample("A", "A", date(2024, 1, 1), 100, 0, features={"ret_20d": 0.3}),
        DailyRallySample("A", "A", date(2024, 1, 2), 110, 0, features={"ret_20d": 0.01}),
        DailyRallySample("B", "B", date(2024, 1, 2), 120, 0, features={"ret_20d": 0.3}),
    ]
    rules = [
        DailyRallyRule("ret_20d>=0.20", "ret_20d >= 0.20", 1, 1, 1, 1.0, 0.5, 2.0, 3.0)
    ]

    candidates = find_current_candidates(samples, rules)

    assert [candidate.ticker for candidate in candidates] == ["B"]
    assert candidates[0].matched_rule_count == 1
    assert candidates[0].max_rule_score == 3.0


def test_run_daily_rally_backtest_returns_result_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    closes = [100.0 + i * 0.1 for i in range(340)]
    closes[220] = closes[200] * 1.5
    daily = _daily_frame(closes)

    monkeypatch.setattr(daily_rally_module, "load_active_universe", lambda db: [("005930", "Samsung")])
    monkeypatch.setattr(
        daily_rally_module,
        "load_daily_ohlcv",
        lambda db, ticker, **kwargs: daily,
    )
    monkeypatch.setattr(daily_rally_module, "load_weekly_ohlcv", lambda db, ticker: pd.DataFrame())

    result = run_daily_rally_backtest(object())

    assert result.ticker_count == 1
    assert result.samples
    assert result.data_start == daily.index.min().date()
    assert result.data_end == daily.index.max().date()
