from __future__ import annotations

import pandas as pd

from scripts.backtest.analysis_similarity import (
    SimilarityProfile,
    analysis_score_bucket,
    bucket_macd_hist,
    bucket_rsi,
    bucket_volume,
    profile_from_features,
    run_similarity_ticker,
    similarity_score,
)
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
