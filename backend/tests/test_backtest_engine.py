import importlib
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

wi = importlib.import_module("weekly_indicators")
from backtest.engine import (  # noqa: E402
    HORIZONS,
    aggregate,
    build_combined,
    run_span2_breakout_ticker,
    run_ticker,
    score_bucket,
)


def _uptrend_combined(weeks: int = 400) -> pd.DataFrame:
    days = weeks * 7
    idx = pd.date_range("2014-01-06", periods=days, freq="D")
    close = 10000 + np.arange(days) * 8.0
    high = close + 30
    low = close - 30
    open_ = close - 5
    vol = np.full(days, 5000.0)
    daily = pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol},
        index=idx,
    )
    weekly = wi.resample_weekly(daily)
    return build_combined(weekly, "005930", "test")


def test_score_bucket_boundaries():
    assert score_bucket(4) == "4-5"
    assert score_bucket(5) == "4-5"
    assert score_bucket(6) == "6-7"
    assert score_bucket(7) == "6-7"
    assert score_bucket(8) == "8+"
    assert score_bucket(12) == "8+"


def test_run_ticker_produces_buy_signals_in_uptrend():
    combined = _uptrend_combined()
    records = run_ticker(combined, warmup=120)

    assert len(records) > 0
    r = records[0]
    assert set(r.returns.keys()) == set(HORIZONS)
    assert r.returns[4] is None or r.returns[4] > 0


def test_forward_return_math_and_censoring():
    combined = _uptrend_combined()
    price = combined[combined["close"].notna()].reset_index(drop=True)
    records = run_ticker(combined, warmup=120)

    last = records[-1]
    i = price.index[price["date"] == last.signal_date.isoformat()][0]
    entry = price["open"].iloc[i + 1]
    for h in HORIZONS:
        j = i + h
        if j < len(price):
            expected = price["close"].iloc[j] / entry - 1
            assert abs(last.returns[h] - expected) < 1e-9
        else:
            assert last.returns[h] is None


def test_aggregate_computes_win_rate_and_distribution():
    combined = _uptrend_combined()
    records = run_ticker(combined, warmup=120)
    stats = aggregate(records)

    all_4w = [s for s in stats if s.horizon == 4 and s.score_bucket == "ALL"]
    assert len(all_4w) == 1
    s = all_4w[0]
    assert s.count >= 0
    if s.count > 0:
        assert 0.0 <= s.win_rate <= 1.0
        assert s.p25 <= s.median <= s.p75


def _span2_frame(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": row_date,
                "ticker": "005930",
                "name": "Samsung",
                "close": close,
                "ichi_lead2": span2,
                "cloud_top": cloud_top,
                "cloud_bottom": cloud_bottom,
            }
            for row_date, close, span2, cloud_top, cloud_bottom in rows
        ]
    )


def test_span2_breakout_enters_only_above_cloud_top_and_stops_below_cloud_bottom():
    combined = _span2_frame(
        [
            ("2024-01-01", 98, 100, 105, 95),
            ("2024-01-08", 106, 100, 105, 95),
            ("2024-01-15", 94, 100, 105, 95),
        ]
    )

    records = run_span2_breakout_ticker(combined, warmup=1)

    assert len(records) == 1
    record = records[0]
    assert record.signal_date == date(2024, 1, 8)
    assert record.entry_date == date(2024, 1, 8)
    assert record.entry_price == 106
    assert record.exit_date == date(2024, 1, 15)
    assert record.exit_reason == "stop"
    assert record.exit_price == 94
    assert record.event_return == pytest.approx(94 / 106 - 1)


def test_span2_breakout_ignores_breakout_below_cloud_top_and_marks_open_at_last_close():
    combined = _span2_frame(
        [
            ("2024-01-01", 98, 100, 105, 95),
            ("2024-01-08", 102, 100, 105, 95),
            ("2024-01-15", 99, 100, 105, 95),
            ("2024-01-22", 106, 100, 105, 95),
            ("2024-01-29", 110, 100, 105, 95),
        ]
    )

    records = run_span2_breakout_ticker(combined, warmup=1)

    assert len(records) == 1
    record = records[0]
    assert record.signal_date == date(2024, 1, 22)
    assert record.exit_date == date(2024, 1, 29)
    assert record.exit_reason == "open"
    assert record.exit_price == 110
    assert record.event_return == pytest.approx(110 / 106 - 1)


def test_span2_breakout_ignores_duplicate_signals_while_held_and_allows_reentry_after_stop():
    combined = _span2_frame(
        [
            ("2024-01-01", 98, 100, 105, 95),
            ("2024-01-08", 106, 100, 105, 95),
            ("2024-01-15", 99, 98, 105, 95),
            ("2024-01-22", 106, 100, 105, 95),
            ("2024-01-29", 94, 100, 105, 95),
            ("2024-02-05", 99, 100, 105, 95),
            ("2024-02-12", 106, 100, 105, 95),
            ("2024-02-19", 108, 100, 105, 95),
        ]
    )

    records = run_span2_breakout_ticker(combined, warmup=1)

    assert [record.signal_date for record in records] == [
        date(2024, 1, 8),
        date(2024, 2, 12),
    ]
    assert [record.exit_reason for record in records] == ["stop", "open"]
