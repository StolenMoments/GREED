from __future__ import annotations

import pandas as pd
import pytest

from backend.models import Analysis
from scripts.backtest.analysis_similarity import (
    SimilarityProfile,
    analysis_score_bucket,
    bucket_macd_hist,
    bucket_rsi,
    bucket_volume,
    contract_event_for_candidate,
    profile_from_features,
    run_analysis_contract_backtest,
    run_similarity_ticker,
    similarity_score,
)
import scripts.backtest.analysis_similarity as analysis_similarity_module
from scripts.rule_scorer.features import extract_features_asof


def _profile(**overrides: str) -> SimilarityProfile:
    data = {
        "trend": "up",
        "cloud_position": "above",
        "ma_alignment": "bullish",
        "macd_hist_direction": "rising_positive",
        "rsi_bucket": "mid",
        "volume_bucket": "active",
        "strict_divergence": "none",
        "future_cloud_direction": "up",
    }
    data.update(overrides)
    return SimilarityProfile(**data)


def test_similarity_score_full_match_is_14() -> None:
    assert similarity_score(_profile(), _profile()) == 14


def test_similarity_score_does_not_reward_unknowns() -> None:
    base = _profile(rsi_bucket="unknown", volume_bucket="unknown")
    candidate = _profile(rsi_bucket="unknown", volume_bucket="unknown")

    assert similarity_score(base, candidate) == 12


def test_bucket_helpers() -> None:
    assert bucket_macd_hist(3.0, 2.0, 1.0) == "rising_positive"
    assert bucket_macd_hist(-3.0, -2.0, -1.0) == "falling_negative"
    assert bucket_macd_hist(None, -2.0, -1.0) == "unknown"
    assert bucket_rsi(35) == "low"
    assert bucket_rsi(55) == "mid"
    assert bucket_rsi(68) == "high"
    assert bucket_rsi(80) == "overheated"
    assert bucket_volume(0.6) == "dry"
    assert bucket_volume(0.9) == "normal"
    assert bucket_volume(1.1) == "active"


def test_analysis_score_bucket() -> None:
    assert analysis_score_bucket(10) == "10"
    assert analysis_score_bucket(11) == "11"
    assert analysis_score_bucket(12) == "12"
    assert analysis_score_bucket(13) == "13"
    assert analysis_score_bucket(14) == "14"


def _combined_frame() -> pd.DataFrame:
    rows = []
    for i in range(150):
        close = 100.0 + i
        rows.append(
            {
                "date": str(pd.Timestamp("2020-01-06") + pd.Timedelta(days=7 * i))[:10],
                "ticker": "000001",
                "name": "Test",
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 1000,
                "trading_value": 100000,
                "ma20": close - 1,
                "ma60": close - 2,
                "ma120": close - 3,
                "atr14": 1,
                "atr14_pct": 0.01,
                "rsi14": 55,
                "macd_hist": 3,
                "volume_ratio_20": 1.2,
                "ichi_conv": close - 1,
                "ichi_base": close - 2,
                "cloud_top": close - 5,
                "cloud_bottom": close - 8,
                "strict_divergence": "",
                "ma20_60_cross": "",
                "ichi_lead1": close + 1,
                "ichi_lead2": close,
            }
        )
    df = pd.DataFrame(rows)
    df["macd_hist"] = [1, 2, *([3] * 148)]
    return df


def test_run_similarity_ticker_emits_records() -> None:
    combined = _combined_frame()
    base, _score, _judgment = profile_from_features(extract_features_asof(combined, 120))

    records = run_similarity_ticker(combined, base_profile=base, threshold=10, warmup=120)

    assert records
    assert records[0].score >= 10
    assert records[0].score_bucket == str(records[0].score)
    assert 4 in records[0].returns


def _daily_frame(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [row[1] for row in rows],
            "high": [row[2] for row in rows],
            "low": [row[3] for row in rows],
            "close": [row[4] for row in rows],
            "volume": [1000 for _ in rows],
            "trading_value": [100000 for _ in rows],
        },
        index=pd.to_datetime([row[0] for row in rows]),
    )


def test_contract_event_waits_for_entry_then_records_target() -> None:
    daily = _daily_frame(
        [
            ("2024-01-02", 100, 103, 99, 102),
            ("2024-01-03", 102, 104, 101, 103),
            ("2024-01-04", 103, 106, 95, 100),
            ("2024-01-05", 100, 112, 99, 111),
        ]
    )

    event = contract_event_for_candidate(
        daily,
        signal_date=pd.Timestamp("2024-01-02").date(),
        entry_price=96,
        target_price=110,
        stop_price=90,
        max_entry_days=20,
        max_hold_days=130,
    )

    assert event.entry_date == pd.Timestamp("2024-01-04").date()
    assert event.exit_date == pd.Timestamp("2024-01-05").date()
    assert event.exit_reason == "target"
    assert event.exit_price == 110
    assert event.event_return == 110 / 96 - 1
    assert event.days_held == 1


def test_contract_event_uses_stop_first_when_target_and_stop_touch_same_day() -> None:
    daily = _daily_frame(
        [
            ("2024-01-02", 100, 103, 99, 102),
            ("2024-01-03", 102, 106, 94, 100),
        ]
    )

    event = contract_event_for_candidate(
        daily,
        signal_date=pd.Timestamp("2024-01-02").date(),
        entry_price=100,
        target_price=105,
        stop_price=95,
        max_entry_days=20,
        max_hold_days=130,
    )

    assert event.exit_reason == "stop"
    assert event.exit_price == 95
    assert event.event_return == pytest.approx(-0.05)


def test_contract_event_ignores_invalid_zero_ohlc_rows() -> None:
    daily = _daily_frame(
        [
            ("2018-04-27", 50000, 51000, 49000, 50000),
            ("2018-04-30", 0, 0, 0, 53000),
            ("2018-05-02", 50000, 52000, 49500, 51000),
            ("2018-05-03", 51000, 56000, 50500, 55500),
        ]
    )

    event = contract_event_for_candidate(
        daily,
        signal_date=pd.Timestamp("2018-04-27").date(),
        entry_price=50000,
        target_price=55000,
        stop_price=48000,
        max_entry_days=1,
        max_hold_days=130,
    )

    assert event.entry_date == pd.Timestamp("2018-05-02").date()
    assert event.exit_reason == "target"
    assert event.exit_date == pd.Timestamp("2018-05-03").date()


def test_contract_event_ignores_invalid_rows_in_hold_window() -> None:
    daily = _daily_frame(
        [
            ("2024-01-02", 100, 101, 99, 100),
            ("2024-01-03", 100, 101, 99, 100),
            ("2024-01-04", 0, 0, 0, 100),
            ("2024-01-05", 100, 111, 99, 110),
        ]
    )

    event = contract_event_for_candidate(
        daily,
        signal_date=pd.Timestamp("2024-01-02").date(),
        entry_price=100,
        target_price=110,
        stop_price=95,
        max_entry_days=20,
        max_hold_days=130,
    )

    assert event.exit_reason == "target"
    assert event.exit_date == pd.Timestamp("2024-01-05").date()


def test_contract_event_expires_at_last_close_after_hold_window() -> None:
    daily = _daily_frame(
        [
            ("2024-01-02", 100, 101, 99, 100),
            ("2024-01-03", 100, 101, 99, 100),
            ("2024-01-04", 100, 102, 98, 101),
        ]
    )

    event = contract_event_for_candidate(
        daily,
        signal_date=pd.Timestamp("2024-01-02").date(),
        entry_price=100,
        target_price=110,
        stop_price=90,
        max_entry_days=20,
        max_hold_days=1,
    )

    assert event.exit_reason == "expiry"
    assert event.exit_date == pd.Timestamp("2024-01-04").date()
    assert event.exit_price == 101
    assert event.event_return == pytest.approx(0.01)


def test_contract_event_reports_no_entry_when_entry_not_touched() -> None:
    daily = _daily_frame(
        [
            ("2024-01-02", 100, 102, 99, 101),
            ("2024-01-03", 101, 103, 100, 102),
        ]
    )

    event = contract_event_for_candidate(
        daily,
        signal_date=pd.Timestamp("2024-01-02").date(),
        entry_price=95,
        target_price=105,
        stop_price=90,
        max_entry_days=1,
        max_hold_days=130,
    )

    assert event.exit_reason == "no_entry"
    assert event.entry_date is None
    assert event.event_return is None


def test_contract_event_changes_when_contract_levels_change_on_same_prices() -> None:
    daily = _daily_frame(
        [
            ("2024-01-02", 100, 101, 99, 100),
            ("2024-01-03", 100, 106, 94, 100),
        ]
    )

    target_first = contract_event_for_candidate(
        daily,
        signal_date=pd.Timestamp("2024-01-02").date(),
        entry_price=100,
        target_price=105,
        stop_price=90,
    )
    stop_first = contract_event_for_candidate(
        daily,
        signal_date=pd.Timestamp("2024-01-02").date(),
        entry_price=100,
        target_price=110,
        stop_price=95,
    )

    assert target_first.exit_reason == "target"
    assert stop_first.exit_reason == "stop"


def test_contract_backtest_requires_buy_analysis_and_contract_prices() -> None:
    analysis = Analysis(
        run_id=1,
        ticker="005930",
        name="Samsung",
        name_initials="SS",
        model="rule",
        markdown="body",
        judgment="hold",
        trend="up",
        cloud_position="above",
        ma_alignment="bullish",
        entry_price=None,
        target_price=120,
        stop_loss=90,
    )

    with pytest.raises(ValueError, match="requires a buy analysis"):
        run_analysis_contract_backtest(None, analysis)

    analysis.judgment = "buy"
    with pytest.raises(ValueError, match="entry_price"):
        run_analysis_contract_backtest(None, analysis)


def test_similarity_backtest_uses_db_universe_by_default(monkeypatch) -> None:
    analysis = Analysis(
        run_id=1,
        ticker="005930",
        name="Samsung",
        name_initials="SS",
        model="rule",
        markdown="body",
        judgment="buy",
        trend="up",
        cloud_position="above",
        ma_alignment="bullish",
        created_at=pd.Timestamp("2024-01-02"),
    )
    weekly = pd.DataFrame({"close": [100.0] * 4}, index=pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22"]))
    calls: list[str] = []

    monkeypatch.setattr(analysis_similarity_module, "load_active_universe", lambda db: [("000660", "SK Hynix")])
    monkeypatch.setattr(analysis_similarity_module, "load_universe", lambda path: pytest.fail("CSV universe should not be used by default"))

    def fake_weekly(db, ticker: str):
        calls.append(ticker)
        return weekly

    monkeypatch.setattr(analysis_similarity_module, "load_weekly_ohlcv", fake_weekly)
    monkeypatch.setattr(analysis_similarity_module, "build_combined", lambda frame, ticker, name: _combined_frame())
    monkeypatch.setattr(analysis_similarity_module, "analysis_asof_index", lambda combined, created_at: 120)
    monkeypatch.setattr(analysis_similarity_module, "run_similarity_ticker", lambda *args, **kwargs: [])
    monkeypatch.setattr(analysis_similarity_module, "aggregate", lambda records, buckets=None: [])

    result = analysis_similarity_module.run_analysis_similarity_backtest(
        object(),
        analysis,
        threshold=10,
        warmup=1,
    )

    assert calls == ["005930", "000660"]
    assert result.ticker_count == 1


def _make_analysis_with_prices() -> Analysis:
    return Analysis(
        id=1,
        run_id=1,
        ticker="000001",
        name="TestCo",
        name_initials="TC",
        model="claude",
        markdown="",
        judgment="매수",
        trend="상승",
        cloud_position="구름 위",
        ma_alignment="정배열",
        entry_price=105.0,
        target_price=145.0,
        stop_loss=88.0,
        created_at=pd.Timestamp("2022-07-11"),
    )


def test_scan_current_candidates_returns_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.backtest.analysis_similarity import scan_current_candidates

    analysis = _make_analysis_with_prices()

    def fake_load_weekly(db, ticker):
        rows = []
        for i in range(150):
            close = 100.0 + i
            rows.append({
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 1000.0,
                "trading_value": 1000.0 * close,
            })
        idx = pd.date_range("2020-01-06", periods=150, freq="W-MON")
        df = pd.DataFrame(rows, index=idx)
        df.index.name = "date"
        return df

    def fake_load_daily(db, ticker, **kwargs):
        rows = []
        for i in range(150 * 5):
            close = 100.0 + i / 5
            rows.append({
                "open": close, "high": close + 1, "low": close - 1,
                "close": close, "volume": 500.0, "trading_value": 500.0 * close,
            })
        idx = pd.date_range("2020-01-02", periods=150 * 5, freq="B")
        df = pd.DataFrame(rows, index=idx)
        df.index.name = "date"
        return df

    monkeypatch.setattr(analysis_similarity_module, "load_weekly_ohlcv", fake_load_weekly)
    monkeypatch.setattr(analysis_similarity_module, "load_daily_ohlcv", fake_load_daily)
    monkeypatch.setattr(
        analysis_similarity_module,
        "load_active_universe",
        lambda db: [("000001", "TestCo")],
    )

    candidates, scan_date = scan_current_candidates(None, analysis, threshold=10)
    assert isinstance(candidates, list)
    assert scan_date is not None
