from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from scripts.backtest import daily_rally as daily_rally_module
from scripts.backtest.daily_rally import (
    DailyRallyCandidate,
    DailyRallyPatternStability,
    DailyRallyPatternStat,
    DailyRallyReturnStat,
    DailyRallyRule,
    DailyRallySample,
    DailyRallyValidationSummary,
    build_daily_rally_validation,
    build_daily_features,
    build_pattern_stats,
    build_samples_for_ticker,
    build_weekly_asof_features,
    find_current_candidates,
    label_daily_rallies,
    rank_rules,
    run_daily_rally_backtest,
    score_candidates,
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

    rules = rank_rules(
        samples,
        min_support=1,
        min_precision=0.1,
        min_total_matches=1,
        min_lift=0.0,
    )
    rule = next(rule for rule in rules if rule.rule_key == "ret_20d>=0.20")

    assert rule.support == 2
    assert rule.positives == 2
    assert rule.total_matches == 3
    assert rule.base_rate == pytest.approx(2 / 6)
    assert rule.precision == pytest.approx(2 / 3)
    assert rule.lift == pytest.approx(2.0)
    assert rule.score == pytest.approx(2 * 1.0 * (2 / 3))


def _combo_mining_samples() -> list[DailyRallySample]:
    samples: list[DailyRallySample] = []
    for index in range(1000):
        features: dict[str, float | bool | str] = {"ret_20d": 0.0, "volume_ratio_20d": 1.0}
        if index < 10:
            label = 1
        else:
            label = 0

        if index < 5 or 10 <= index < 200:
            features["ret_20d"] = 0.12
        if index < 5 or 10 <= index < 105 or 200 <= index < 295:
            features["volume_ratio_20d"] = 2.5

        samples.append(
            DailyRallySample(
                ticker=f"T{index:04d}",
                name=f"Ticker {index}",
                signal_date=date(2024, 1, 1),
                close_price=100,
                label=label,
                features=features,
            )
        )
    return samples


def test_rank_rules_mines_combo_when_single_rules_are_below_precision_gate() -> None:
    rules = rank_rules(_combo_mining_samples())

    combo = next(
        rule
        for rule in rules
        if rule.rule_key == "ret_20d>=0.10&volume_ratio_20d>=2.00"
    )

    assert combo.support == 5
    assert combo.total_matches == 100
    assert combo.precision == pytest.approx(0.05)
    assert combo.base_rate == pytest.approx(0.01)
    assert combo.lift == pytest.approx(5.0)


def test_rank_rules_does_not_combine_thresholds_from_same_feature() -> None:
    samples = [
        DailyRallySample("A", "A", date(2024, 1, 1), 100, 1, features={"ret_20d": 0.3}),
        DailyRallySample("B", "B", date(2024, 1, 1), 100, 0, features={"ret_20d": 0.25}),
    ]

    rules = rank_rules(samples, min_support=1, min_precision=0.0, min_lift=0.0, min_total_matches=1)

    assert all(
        "ret_20d>=0.10&ret_20d>=0.20" not in rule.rule_key
        and "ret_20d>=0.20&ret_20d>=0.10" not in rule.rule_key
        for rule in rules
    )


def test_rank_rules_includes_three_condition_combos_sorted_by_score() -> None:
    samples = _combo_mining_samples()
    for index, sample in enumerate(samples):
        sample.features["range_pct"] = 0.02
        if index < 5 or 10 <= index < 55:
            sample.features["range_pct"] = 0.09

    rules = rank_rules(samples)
    keys = [rule.rule_key for rule in rules]
    triple_key = "ret_20d>=0.10&volume_ratio_20d>=2.00&range_pct>=0.08"
    double_key = "ret_20d>=0.10&volume_ratio_20d>=2.00"

    triple = next(rule for rule in rules if rule.rule_key == triple_key)
    double = next(rule for rule in rules if rule.rule_key == double_key)

    assert triple.total_matches == 50
    assert triple.precision == pytest.approx(0.10)
    assert triple.score > double.score
    assert keys.index(triple_key) < keys.index(double_key)


def test_build_pattern_stats_keeps_unfiltered_single_patterns_with_return_stats() -> None:
    samples = [
        DailyRallySample(
            "A",
            "A",
            date(2024, 1, 1),
            100,
            1,
            forward_returns={20: 0.5, 40: 0.7, 60: None, 120: 1.0},
            features={"ret_20d": 0.3},
        ),
        DailyRallySample(
            "B",
            "B",
            date(2024, 1, 1),
            100,
            0,
            forward_returns={20: -0.1, 40: 0.2, 60: 0.3, 120: None},
            features={"ret_20d": 0.25},
        ),
        DailyRallySample(
            "C",
            "C",
            date(2024, 1, 1),
            100,
            0,
            forward_returns={20: 0.1, 40: None, 60: 0.4, 120: 0.6},
            features={"ret_20d": 0.01},
        ),
    ]

    stats = build_pattern_stats(samples)
    stat = next(pattern for pattern in stats if pattern.pattern_key == "ret_20d>=0.20")

    assert stat.support == 1
    assert stat.positives == 1
    assert stat.total_matches == 2
    assert stat.base_rate == pytest.approx(1 / 3)
    assert stat.precision == pytest.approx(1 / 2)
    assert stat.lift == pytest.approx(1.5)
    assert stat.score == pytest.approx(1 * 0.5 * 0.5)
    assert stat.return_stats[20].count == 2
    assert stat.return_stats[20].mean == pytest.approx(0.2)
    assert stat.return_stats[40].count == 2
    assert stat.return_stats[40].mean == pytest.approx(0.45)
    assert stat.return_stats[60].count == 1
    assert stat.return_stats[60].censored_count == 1
    assert stat.return_stats[120].count == 1
    assert stat.return_stats[120].censored_count == 1


def test_run_daily_rally_backtest_returns_pattern_stats_when_strict_rules_are_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    samples = [
        DailyRallySample("A", "A", date(2024, 1, 1), 100, 1, features={"ret_20d": 0.3}),
        DailyRallySample("B", "B", date(2024, 1, 2), 100, 0, features={"ret_20d": 0.25}),
    ]

    monkeypatch.setattr(
        daily_rally_module,
        "_collect_daily_rally_samples",
        lambda db, universe=None: (samples, 2, date(2024, 1, 1), date(2024, 1, 2)),
    )
    monkeypatch.setattr(daily_rally_module, "rank_rules", lambda samples: [])

    result = run_daily_rally_backtest(object())

    assert result.rules == []
    assert result.current_candidates == []
    assert any(pattern.pattern_key == "ret_20d>=0.20" for pattern in result.pattern_stats)


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


def _score_rule(rule_key: str, score: float) -> DailyRallyRule:
    return DailyRallyRule(rule_key, rule_key, 5, 5, 50, 0.1, 0.02, 5.0, score)


def _score_pattern(
    pattern_key: str,
    *,
    win_rate: float | None,
    median_return: float | None,
    count: int = 50,
) -> DailyRallyPatternStat:
    return DailyRallyPatternStat(
        pattern_key=pattern_key,
        pattern_label=pattern_key,
        support=5,
        positives=5,
        total_matches=50,
        precision=0.1,
        base_rate=0.02,
        lift=5.0,
        score=2.0,
        return_stats={
            20: DailyRallyReturnStat(
                horizon=20,
                count=count,
                censored_count=0,
                win_rate=win_rate,
                mean=median_return,
                median=median_return,
                std=None,
                p25=None,
                p75=None,
                min=None,
                max=None,
            )
        },
    )


def _score_validation(classifications: dict[str, str]) -> DailyRallyValidationSummary:
    return DailyRallyValidationSummary(
        summary={},
        year_breakdown=[],
        ticker_concentration=[],
        pattern_stability=[
            DailyRallyPatternStability(
                pattern_key=key,
                pattern_label=key,
                total_matches=50,
                positives=5,
                full_period_lift=5.0,
                test_window_count=5,
                median_train_lift=2.0,
                median_test_lift=1.5,
                test_lift_gt_1_ratio=0.8,
                classification=classification,
            )
            for key, classification in classifications.items()
        ],
        walk_forward_windows=[],
        warnings=[],
    )


def _score_candidate(matched_rules: list[str], *, max_rule_score: float) -> DailyRallyCandidate:
    return DailyRallyCandidate(
        ticker="A",
        name="A",
        signal_date=date(2024, 1, 2),
        close_price=100,
        matched_rules=matched_rules,
        matched_rule_count=len(matched_rules),
        max_rule_score=max_rule_score,
        mean_rule_score=max_rule_score,
    )


def test_score_candidates_computes_composite_from_quality_stability_and_return() -> None:
    rules = [_score_rule("ret_20d>=0.20", 10.0)]
    patterns = [_score_pattern("ret_20d>=0.20", win_rate=0.6, median_return=0.20)]
    validation = _score_validation({"ret_20d>=0.20": "stable"})
    candidate = _score_candidate(["ret_20d>=0.20"], max_rule_score=10.0)

    scored = score_candidates([candidate], rules, patterns, validation)[0]

    # RQ = log1p(10)/log1p(10) = 1.0, ER = 0.5*0.6 + 0.5*(0.20/0.40) = 0.55, STAB = 1.0
    assert scored.composite_score == pytest.approx(100 * (0.5 * 1.0 + 0.5 * 0.55))
    assert scored.best_rule_key == "ret_20d>=0.20"
    assert scored.rule_quality_score == pytest.approx(1.0)
    assert scored.stability_score == pytest.approx(1.0)
    assert scored.stability_classification == "stable"
    assert scored.expected_return_score == pytest.approx(0.55)
    assert scored.expected_win_rate_20d == pytest.approx(0.6)
    assert scored.expected_median_return_20d == pytest.approx(0.20)
    assert len(scored.rule_breakdowns) == 1


def test_score_candidates_combo_stability_uses_worst_component() -> None:
    combo_key = "ret_20d>=0.20&volume_ratio_20d>=2.00"
    rules = [_score_rule(combo_key, 10.0)]
    patterns = [_score_pattern(combo_key, win_rate=1.0, median_return=0.40)]
    validation = _score_validation(
        {"ret_20d>=0.20": "stable", "volume_ratio_20d>=2.00": "fragile"}
    )
    candidate = _score_candidate([combo_key], max_rule_score=10.0)

    scored = score_candidates([candidate], rules, patterns, validation)[0]

    assert scored.stability_score == pytest.approx(0.6)
    assert scored.stability_classification == "fragile"
    assert scored.composite_score == pytest.approx(100 * (0.5 * 1.0 + 0.5 * 1.0) * 0.6)


def test_score_candidates_treats_missing_pattern_stat_as_zero_expected_return() -> None:
    rules = [_score_rule("ret_20d>=0.20", 10.0)]
    validation = _score_validation({"ret_20d>=0.20": "stable"})
    candidate = _score_candidate(["ret_20d>=0.20"], max_rule_score=10.0)

    scored = score_candidates([candidate], rules, [], validation)[0]

    assert scored.expected_return_score == pytest.approx(0.0)
    assert scored.expected_win_rate_20d is None
    assert scored.composite_score == pytest.approx(100 * 0.5 * 1.0)


def test_score_candidates_without_validation_defaults_to_insufficient_multiplier() -> None:
    rules = [_score_rule("ret_20d>=0.20", 10.0)]
    patterns = [_score_pattern("ret_20d>=0.20", win_rate=1.0, median_return=0.40)]
    candidate = _score_candidate(["ret_20d>=0.20"], max_rule_score=10.0)

    scored = score_candidates([candidate], rules, patterns, None)[0]

    assert scored.stability_score == pytest.approx(0.4)
    assert scored.stability_classification == "insufficient"
    assert scored.composite_score == pytest.approx(100 * 1.0 * 0.4)


def test_score_candidates_resorts_by_composite_over_max_rule_score() -> None:
    rules = [_score_rule("fragile_rule>=1", 20.0), _score_rule("stable_rule>=1", 10.0)]
    patterns = [
        _score_pattern("fragile_rule>=1", win_rate=1.0, median_return=0.40),
        _score_pattern("stable_rule>=1", win_rate=1.0, median_return=0.40),
    ]
    validation = _score_validation({"fragile_rule>=1": "fragile", "stable_rule>=1": "stable"})
    fragile_candidate = _score_candidate(["fragile_rule>=1"], max_rule_score=20.0)
    fragile_candidate.ticker = "FRAGILE"
    stable_candidate = _score_candidate(["stable_rule>=1"], max_rule_score=10.0)
    stable_candidate.ticker = "STABLE"

    scored = score_candidates([fragile_candidate, stable_candidate], rules, patterns, validation)

    assert [candidate.ticker for candidate in scored] == ["STABLE", "FRAGILE"]
    assert scored[0].composite_score > scored[1].composite_score


def test_score_candidates_caps_breadth_bonus_and_total_score() -> None:
    rules = [_score_rule("ret_20d>=0.20", 10.0)]
    patterns = [_score_pattern("ret_20d>=0.20", win_rate=1.0, median_return=0.24)]
    validation = _score_validation({"ret_20d>=0.20": "stable"})
    candidate = _score_candidate(["ret_20d>=0.20"], max_rule_score=10.0)
    candidate.matched_rule_count = 10

    scored = score_candidates([candidate], rules, patterns, validation)[0]

    # ER = 0.5*1.0 + 0.5*(0.24/0.40) = 0.8 → rule_composite = 90; bonus capped at 1.2 → 108 → 100
    assert scored.rule_breakdowns[0].rule_composite == pytest.approx(90.0)
    assert scored.composite_score == pytest.approx(100.0)


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


def _validation_sample(
    ticker: str,
    signal_date: date,
    label: int,
    *,
    ret_20d: float = 0.3,
    ret_120d: float | None = 0.1,
) -> DailyRallySample:
    return DailyRallySample(
        ticker=ticker,
        name=f"Name {ticker}",
        signal_date=signal_date,
        close_price=100,
        label=label,
        forward_returns={120: ret_120d},
        features={"ret_20d": ret_20d},
    )


def test_build_daily_rally_validation_marks_partial_year_and_excludes_it_from_windows() -> None:
    samples = [
        _validation_sample("A", date(2023, 1, 2), 1, ret_120d=0.4),
        _validation_sample("B", date(2023, 1, 3), 0, ret_120d=-0.1),
        _validation_sample("C", date(2026, 6, 1), 1, ret_120d=None),
        _validation_sample("D", date(2026, 6, 2), 0, ret_120d=None),
    ]

    validation = build_daily_rally_validation(samples)

    by_year = {item.year: item for item in validation.year_breakdown}
    assert by_year[2023].partial is False
    assert by_year[2023].base_rate == pytest.approx(0.5)
    assert by_year[2023].positive_forward_return_120d_mean == pytest.approx(0.4)
    assert by_year[2026].partial is True
    assert by_year[2026].censored_120d_count == 2
    assert any("2026" in warning for warning in validation.warnings)
    assert validation.summary["partial_years"] == [2026]


def test_build_daily_rally_validation_sorts_ticker_concentration_by_positive_share() -> None:
    samples = [
        _validation_sample("A", date(2022, 1, 1), 1),
        _validation_sample("A", date(2022, 1, 2), 1),
        _validation_sample("A", date(2022, 1, 3), 0),
        _validation_sample("B", date(2022, 1, 1), 1),
        _validation_sample("C", date(2022, 1, 1), 0),
    ]

    validation = build_daily_rally_validation(samples)

    assert [item.ticker for item in validation.ticker_concentration[:2]] == ["A", "B"]
    assert validation.ticker_concentration[0].positive_count == 2
    assert validation.ticker_concentration[0].positive_share == pytest.approx(2 / 3)


def test_build_daily_rally_validation_walk_forward_does_not_train_on_test_year() -> None:
    samples: list[DailyRallySample] = []
    for year in (2015, 2016, 2017):
        samples.extend(
            [
                _validation_sample("A", date(year, 1, 2), 1, ret_20d=0.3),
                _validation_sample("B", date(year, 1, 3), 0, ret_20d=0.01),
            ]
        )
    samples.extend(
        [
            _validation_sample("C", date(2018, 1, 2), 1, ret_20d=0.01),
            _validation_sample("D", date(2018, 1, 3), 0, ret_20d=0.3),
        ]
    )

    validation = build_daily_rally_validation(samples, min_train_support=1, min_test_matches=1)

    window = validation.walk_forward_windows[0]
    assert window.train_years == [2015, 2016, 2017]
    assert window.test_year == 2018
    assert window.pattern_key == "ret_20d>=0.10"
    assert window.train_lift == pytest.approx(2.0)
    assert window.test_lift == pytest.approx(0.0)


def test_build_daily_rally_validation_classifies_stable_fragile_and_insufficient_patterns() -> None:
    samples: list[DailyRallySample] = []
    for year in range(2015, 2023):
        samples.extend(
            [
                _validation_sample("A", date(year, 1, 2), 1, ret_20d=0.3),
                _validation_sample("B", date(year, 1, 3), 0, ret_20d=0.01),
                _validation_sample("C", date(year, 1, 4), 0, ret_20d=0.01),
            ]
        )

    stable = build_daily_rally_validation(samples, min_train_support=1, min_test_matches=1)
    stable_ret20 = next(item for item in stable.pattern_stability if item.pattern_key == "ret_20d>=0.20")
    assert stable_ret20.classification == "stable"
    assert stable_ret20.test_window_count >= 5
    assert stable_ret20.median_test_lift is not None
    assert stable_ret20.median_test_lift >= 1.2

    fragile_samples = samples.copy()
    for year in range(2018, 2023):
        fragile_samples.extend(
            [
                _validation_sample("D", date(year, 2, 1), 0, ret_20d=0.3),
                _validation_sample("E", date(year, 2, 2), 0, ret_20d=0.3),
                _validation_sample("F", date(year, 2, 3), 0, ret_20d=0.3),
                _validation_sample("G", date(year, 2, 4), 1, ret_20d=0.01),
            ]
        )
    fragile = build_daily_rally_validation(fragile_samples, min_train_support=1, min_test_matches=1)
    fragile_ret20 = next(item for item in fragile.pattern_stability if item.pattern_key == "ret_20d>=0.20")
    assert fragile_ret20.classification == "fragile"

    insufficient = build_daily_rally_validation(samples[:4], min_train_support=1, min_test_matches=1)
    insufficient_ret20 = next(
        item for item in insufficient.pattern_stability if item.pattern_key == "ret_20d>=0.20"
    )
    assert insufficient_ret20.classification == "insufficient"
