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
from rule_scorer.features import extract_features, extract_features_asof  # noqa: E402


def _combined(days: int = 1000) -> pd.DataFrame:
    idx = pd.date_range("2014-01-01", periods=days, freq="D")
    rng = np.random.default_rng(11)
    close = 20000 + np.cumsum(rng.normal(0, 120, days))
    high = close + rng.uniform(20, 200, days)
    low = close - rng.uniform(20, 200, days)
    open_ = close + rng.normal(0, 60, days)
    vol = rng.integers(1_000, 20_000, days)
    daily = pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol},
        index=idx,
    )
    weekly = wi.add_all_indicators(wi.resample_weekly(daily))
    combined = wi.append_future_cloud(weekly).reset_index()
    combined["date"] = combined["date"].astype(str).str.slice(0, 10)
    combined["ticker"] = "005930"
    combined["name"] = "test"
    return combined


def test_asof_at_last_index_matches_extract_features():
    combined = _combined()
    price = combined[combined["close"].notna()]
    ref = extract_features(combined)
    asof = extract_features_asof(combined, len(price) - 1)
    assert asof.asof_date == ref.asof_date
    assert asof.close == ref.close
    assert asof.ma20 == ref.ma20
    assert asof.macd_hist == ref.macd_hist
    assert asof.strict_divergence == ref.strict_divergence
    assert asof.future_cloud_direction == ref.future_cloud_direction


def test_asof_is_leak_free_against_truncation():
    combined = _combined()
    price = combined[combined["close"].notna()].reset_index(drop=True)
    i = len(price) - 60

    full = extract_features_asof(combined, i)

    weekly_trunc = price.iloc[: i + 1][["open", "high", "low", "close", "volume", "trading_value"]].copy()
    weekly_trunc.index = pd.to_datetime(price["date"].iloc[: i + 1])
    weekly_trunc.index.name = "date"
    rebuilt = wi.add_all_indicators(weekly_trunc)
    rebuilt = wi.append_future_cloud(rebuilt).reset_index()
    rebuilt["date"] = rebuilt["date"].astype(str).str.slice(0, 10)
    rebuilt["ticker"] = "005930"
    rebuilt["name"] = "test"
    trunc = extract_features_asof(rebuilt, i)

    assert full.strict_divergence == trunc.strict_divergence
    assert full.future_cloud_direction == trunc.future_cloud_direction
    assert full.ma20 == trunc.ma20
    assert full.rsi14 == trunc.rsi14
