import importlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

wi = importlib.import_module("weekly_indicators")


def _daily(days: int = 900) -> pd.DataFrame:
    idx = pd.date_range("2015-01-01", periods=days, freq="D")
    rng = np.random.default_rng(7)
    close = 10000 + np.cumsum(rng.normal(0, 80, days))
    high = close + rng.uniform(10, 120, days)
    low = close - rng.uniform(10, 120, days)
    open_ = close + rng.normal(0, 40, days)
    vol = rng.integers(1_000, 10_000, days)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol},
        index=idx,
    )


def test_resample_weekly_columns_and_monotonic():
    weekly = wi.resample_weekly(_daily())
    assert list(weekly.columns) == ["open", "high", "low", "close", "volume", "trading_value"]
    assert weekly.index.is_monotonic_increasing
    assert weekly["high"].ge(weekly["low"]).all()


def test_add_all_indicators_adds_expected_columns():
    weekly = wi.resample_weekly(_daily())
    out = wi.add_all_indicators(weekly)
    for col in (
        "ma20",
        "ma60",
        "ma120",
        "atr14",
        "rsi14",
        "macd_hist",
        "ichi_conv",
        "ichi_base",
        "ichi_lead1",
        "ichi_lead2",
        "cloud_top",
        "cloud_bottom",
        "strict_divergence",
        "ma20_60_cross",
    ):
        assert col in out.columns
    assert out["ichi_lead1"].iloc[:26].isna().all()


def test_append_future_cloud_adds_26_future_rows():
    weekly = wi.add_all_indicators(wi.resample_weekly(_daily()))
    combined = wi.append_future_cloud(weekly)
    future = combined[combined["close"].isna()]
    assert len(future) == 26
    assert future["ichi_lead1"].notna().all()
