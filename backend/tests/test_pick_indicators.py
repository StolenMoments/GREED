import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

sys.modules.setdefault("FinanceDataReader", SimpleNamespace())
pick = importlib.import_module("pick")
pick_us = importlib.import_module("pick_us")


NEW_INDICATOR_COLS = [
    "atr14",
    "atr14_pct",
    "rsi14",
    "macd",
    "macd_signal",
    "macd_hist",
]

SIGNAL_COLS = [
    "ma20_60_cross",
    "ma60_120_cross",
    "macd_signal_cross",
    "rsi_divergence",
    "macd_hist_divergence",
    "strict_divergence",
]


def make_weekly(rows: int = 90) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=rows, freq="W-MON")
    closes = [100 + i + ((-1) ** i * 3) for i in range(rows)]
    return pd.DataFrame(
        {
            "open": [close - 1 for close in closes],
            "high": [close + 4 for close in closes],
            "low": [close - 5 for close in closes],
            "close": closes,
            "volume": [1000 + i * 10 for i in range(rows)],
            "trading_value": [(1000 + i * 10) * close for i, close in enumerate(closes)],
        },
        index=index,
    )


def add_all_indicators(module, df: pd.DataFrame) -> pd.DataFrame:
    df = module.add_moving_averages(df)
    df = module.add_liquidity_indicators(df)
    df = module.add_volatility_indicators(df)
    df = module.add_momentum_indicators(df)
    df = module.add_signal_indicators(df)
    df = module.add_ichimoku(df)
    df = module.add_ichimoku_derived_indicators(df)
    return df


def test_pick_adds_volatility_and_momentum_indicators() -> None:
    df = add_all_indicators(pick, make_weekly())
    last = df.iloc[-1]

    for column in NEW_INDICATOR_COLS:
        assert column in df.columns
        assert pd.notna(last[column])

    assert 0 <= last["rsi14"] <= 100
    assert last["atr14"] > 0
    assert last["atr14_pct"] > 0


def test_pick_csv_output_includes_new_indicators_and_empty_future_values(tmp_path: Path) -> None:
    df = add_all_indicators(pick, make_weekly())
    df = pick.append_future_cloud(df)

    csv_path = pick.save_csv(df, "005930", "Samsung", str(tmp_path))
    saved = pd.read_csv(csv_path)
    future_rows = df[df["open"].isna()]
    saved_future_rows = saved[saved["open"].isna()]

    assert len(future_rows) == 26
    assert future_rows[NEW_INDICATOR_COLS + SIGNAL_COLS].isna().all().all()
    assert saved_future_rows[NEW_INDICATOR_COLS + SIGNAL_COLS].isna().all().all()
    for column in NEW_INDICATOR_COLS + SIGNAL_COLS:
        assert column in saved.columns


def test_pick_us_adds_same_indicator_columns() -> None:
    df = add_all_indicators(pick_us, make_weekly())
    last = df.iloc[-1]

    for column in NEW_INDICATOR_COLS:
        assert column in df.columns
        assert pd.notna(last[column])

    for column in SIGNAL_COLS:
        assert column in df.columns


def make_signal_frame(rows: int = 60) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=rows, freq="W-MON")
    return pd.DataFrame(
        {
            "low": [100.0] * rows,
            "high": [110.0] * rows,
            "ma20": [100.0] * rows,
            "ma60": [100.0] * rows,
            "ma120": [100.0] * rows,
            "macd": [0.0] * rows,
            "macd_signal": [0.0] * rows,
            "rsi14": [50.0] * rows,
            "macd_hist": [0.0] * rows,
        },
        index=index,
    )


def test_signal_indicators_mark_cross_events() -> None:
    df = make_signal_frame()
    df.loc[df.index[10], ["ma20", "ma60"]] = [99.0, 100.0]
    df.loc[df.index[11], ["ma20", "ma60"]] = [101.0, 100.0]
    df.loc[df.index[20], ["ma60", "ma120"]] = [101.0, 100.0]
    df.loc[df.index[21], ["ma60", "ma120"]] = [99.0, 100.0]
    df.loc[df.index[30], ["macd", "macd_signal"]] = [-1.0, 0.0]
    df.loc[df.index[31], ["macd", "macd_signal"]] = [1.0, 0.0]
    df.loc[df.index[40], ["macd", "macd_signal"]] = [1.0, 0.0]
    df.loc[df.index[41], ["macd", "macd_signal"]] = [-1.0, 0.0]

    df = pick.add_signal_indicators(df)

    assert df.loc[df.index[11], "ma20_60_cross"] == "golden"
    assert df.loc[df.index[21], "ma60_120_cross"] == "dead"
    assert df.loc[df.index[31], "macd_signal_cross"] == "bullish"
    assert df.loc[df.index[41], "macd_signal_cross"] == "bearish"


def test_signal_indicators_mark_strict_bullish_divergence() -> None:
    df = make_signal_frame()
    df.loc[df.index[10], ["low", "rsi14", "macd_hist"]] = [90.0, 30.0, -2.0]
    df.loc[df.index[20], ["low", "rsi14", "macd_hist"]] = [80.0, 35.0, -1.0]

    df = pick.add_signal_indicators(df)

    assert df.loc[df.index[20], "rsi_divergence"] == "bullish"
    assert df.loc[df.index[20], "macd_hist_divergence"] == "bullish"
    assert df.loc[df.index[20], "strict_divergence"] == "bullish"


def test_signal_indicators_require_both_momentum_divergences_for_strict_signal() -> None:
    df = make_signal_frame()
    df.loc[df.index[10], ["low", "rsi14", "macd_hist"]] = [90.0, 30.0, -2.0]
    df.loc[df.index[20], ["low", "rsi14", "macd_hist"]] = [80.0, 35.0, -3.0]

    df = pick.add_signal_indicators(df)

    assert df.loc[df.index[20], "rsi_divergence"] == "bullish"
    assert pd.isna(df.loc[df.index[20], "macd_hist_divergence"])
    assert pd.isna(df.loc[df.index[20], "strict_divergence"])


def test_signal_indicators_mark_strict_bearish_divergence_for_us_module() -> None:
    df = make_signal_frame()
    df.loc[df.index[10], ["high", "rsi14", "macd_hist"]] = [120.0, 70.0, 2.0]
    df.loc[df.index[20], ["high", "rsi14", "macd_hist"]] = [130.0, 65.0, 1.0]

    df = pick_us.add_signal_indicators(df)

    assert df.loc[df.index[20], "rsi_divergence"] == "bearish"
    assert df.loc[df.index[20], "macd_hist_divergence"] == "bearish"
    assert df.loc[df.index[20], "strict_divergence"] == "bearish"
