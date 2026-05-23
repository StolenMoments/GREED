from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from backend.parser import parse_markdown  # noqa: E402
from rule_scorer import (  # noqa: E402
    compute_levels,
    extract_features,
    render_markdown,
    score_features,
)


WEEKS_TOTAL = 200
FUTURE_WEEKS = 26


def _base_columns() -> list[str]:
    return [
        "date", "ticker", "name",
        "open", "high", "low", "close", "volume",
        "trading_value", "volume_ma20", "volume_ratio_20",
        "ma20", "ma60", "ma120",
        "atr14", "atr14_pct", "rsi14", "macd", "macd_signal", "macd_hist",
        "ma20_60_cross", "ma60_120_cross", "macd_signal_cross",
        "rsi_divergence", "macd_hist_divergence", "strict_divergence",
        "ichi_conv", "ichi_base", "ichi_lead1", "ichi_lead2", "ichi_lag",
        "cloud_top", "cloud_bottom", "cloud_thickness",
        "cloud_thickness_pct", "close_vs_cloud_top_pct", "conv_base_gap_pct",
    ]


def _make_df(direction: str) -> pd.DataFrame:
    """direction = 'up' (정배열+구름위) | 'down' (역배열+구름아래)."""
    rng = pd.date_range("2023-01-02", periods=WEEKS_TOTAL, freq="W-MON")
    base = 100.0
    if direction == "up":
        prices = base + np.arange(WEEKS_TOTAL) * 1.0  # steady rise
    else:
        prices = base + (WEEKS_TOTAL - np.arange(WEEKS_TOTAL)) * 1.0  # steady fall

    df = pd.DataFrame({col: pd.NA for col in _base_columns()}, index=range(WEEKS_TOTAL))
    df["date"] = rng.strftime("%Y-%m-%d")
    df["ticker"] = "005930"
    df["name"] = "테스트종목"
    df["open"] = prices
    df["high"] = prices + 2
    df["low"] = prices - 2
    df["close"] = prices
    df["volume"] = 1_000_000
    df["trading_value"] = prices * 1_000_000
    df["volume_ma20"] = 900_000
    df["volume_ratio_20"] = 1.2
    df["atr14"] = 3.0
    df["atr14_pct"] = 1.5
    df["rsi14"] = 55.0 if direction == "up" else 35.0

    if direction == "up":
        df["ma20"] = prices - 5
        df["ma60"] = prices - 15
        df["ma120"] = prices - 25
        df["macd"] = 1.5
        df["macd_signal"] = 1.0
        df["macd_hist"] = 0.5
        df["ichi_conv"] = prices - 3
        df["ichi_base"] = prices - 8
        df["ichi_lead1"] = prices - 10
        df["ichi_lead2"] = prices - 20
        df["cloud_top"] = prices - 10
        df["cloud_bottom"] = prices - 20
    else:
        df["ma20"] = prices + 5
        df["ma60"] = prices + 15
        df["ma120"] = prices + 25
        df["macd"] = -1.5
        df["macd_signal"] = -1.0
        df["macd_hist"] = -0.5
        df["ichi_conv"] = prices + 3
        df["ichi_base"] = prices + 8
        df["ichi_lead1"] = prices + 10
        df["ichi_lead2"] = prices + 20
        df["cloud_top"] = prices + 20
        df["cloud_bottom"] = prices + 10

    # Make macd_hist trend monotonic so 2주 연속 증감 트리거
    if direction == "up":
        df["macd_hist"] = np.linspace(0.1, 1.0, WEEKS_TOTAL)
    else:
        df["macd_hist"] = np.linspace(-0.1, -1.0, WEEKS_TOTAL)

    # Append future cloud rows (no OHLC)
    future_idx = pd.date_range(rng[-1] + pd.offsets.Week(1), periods=FUTURE_WEEKS, freq="W-MON")
    future_df = pd.DataFrame({col: pd.NA for col in _base_columns()}, index=range(FUTURE_WEEKS))
    future_df["date"] = future_idx.strftime("%Y-%m-%d")
    future_df["ticker"] = "005930"
    future_df["name"] = "테스트종목"
    if direction == "up":
        future_df["ichi_lead1"] = np.linspace(250.0, 280.0, FUTURE_WEEKS)
        future_df["ichi_lead2"] = np.linspace(240.0, 260.0, FUTURE_WEEKS)
    else:
        future_df["ichi_lead1"] = np.linspace(50.0, 30.0, FUTURE_WEEKS)
        future_df["ichi_lead2"] = np.linspace(60.0, 50.0, FUTURE_WEEKS)

    combined = pd.concat([df, future_df], ignore_index=True)
    # Convert to numeric where possible
    for col in combined.columns:
        if col in ("date", "ticker", "name",
                   "ma20_60_cross", "ma60_120_cross", "macd_signal_cross",
                   "rsi_divergence", "macd_hist_divergence", "strict_divergence"):
            continue
        combined[col] = pd.to_numeric(combined[col], errors="coerce")
    return combined


def test_bullish_structure_yields_buy_and_passes_parser() -> None:
    df = _make_df("up")
    features = extract_features(df)
    score = score_features(features)
    assert score.judgment == "매수", f"score={score.total}"
    assert score.cloud_position == "구름 위"
    assert score.ma_alignment == "정배열"

    levels = compute_levels(features, score.judgment)
    markdown = render_markdown(features, score, levels)
    result = parse_markdown(markdown)
    assert result.success, f"failed={result.failed}\n{markdown}"
    assert result.data["judgment"] == "매수"
    assert result.data["trend"] == "상승"
    assert result.data["cloud_position"] == "구름 위"
    assert result.data["ma_alignment"] == "정배열"
    assert result.data["entry_price"] is not None
    assert result.data["target_price"] is not None
    assert result.data["stop_loss"] is not None


def test_bearish_structure_yields_sell_and_passes_parser() -> None:
    df = _make_df("down")
    features = extract_features(df)
    score = score_features(features)
    assert score.judgment == "매도", f"score={score.total}"
    assert score.cloud_position == "구름 아래"
    assert score.ma_alignment == "역배열"

    levels = compute_levels(features, score.judgment)
    markdown = render_markdown(features, score, levels)
    result = parse_markdown(markdown)
    assert result.success, f"failed={result.failed}\n{markdown}"
    assert result.data["judgment"] == "매도"
    assert result.data["trend"] == "하락"
    assert result.data["cloud_position"] == "구름 아래"
    assert result.data["ma_alignment"] == "역배열"
