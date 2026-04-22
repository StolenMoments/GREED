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
gogo2 = importlib.import_module("gogo2")


def make_weekly(close: float = 96.0, volume: float = 1000.0, rows: int = 180) -> pd.DataFrame:
    closes = [close] * rows
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [value + 2 for value in closes],
            "Low": [value - 2 for value in closes],
            "Close": closes,
            "Volume": [volume] * rows,
        }
    )


def install_fake_indicators(monkeypatch):
    def fake_ichimoku(df: pd.DataFrame) -> pd.DataFrame:
        df["span_a"] = 100.0
        df["span_b"] = 90.0
        df["tenkan"] = 105.0
        df["kijun"] = 98.0
        df["chikou"] = df["Close"].shift(-26)
        return df

    def fake_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
        df["ma20"] = 95.0
        df["ma60"] = 91.0
        df["ma120"] = 88.0
        df["volume_ma20"] = 1000.0
        df.loc[df.index[-3], "ma20"] = 94.0
        df.loc[df.index[-2], "ma20"] = 96.0
        df.loc[df.index[-3], "ma60"] = 90.0
        df.loc[df.index[-2], "ma60"] = 92.0
        return df

    monkeypatch.setattr(gogo2, "ichimoku", fake_ichimoku)
    monkeypatch.setattr(gogo2, "moving_averages", fake_moving_averages)


def test_breakout_passes_even_when_volume_is_below_old_required_multiplier(monkeypatch):
    install_fake_indicators(monkeypatch)
    df = make_weekly()
    df.loc[df.index[-3], "Close"] = 99.0
    df.loc[df.index[-2], "Close"] = 103.0

    hit, detail = gogo2.check_conditions(df, candle_cloud_lookback=8, ma_cloud_lookback=4, gc_lookback=4)

    assert hit is True
    assert detail["scan_type"] == "breakout"
    assert detail["캔들구름돌파_N주전"] == 0
    assert detail["거래량4주비율"] == 1.0
    assert detail["돌파시거래량증가(배)"] == 1.0


def test_pre_breakout_detects_stock_near_cloud_top_without_breakout(monkeypatch):
    install_fake_indicators(monkeypatch)
    df = make_weekly(close=96.0)
    df.loc[df.index[-2], "Close"] = 97.0

    hit, detail = gogo2.check_conditions(df, candle_cloud_lookback=8, ma_cloud_lookback=4, gc_lookback=4)

    assert hit is True
    assert detail["scan_type"] == "pre_breakout"
    assert detail["캔들구름돌파_N주전"] is None
    assert detail["돌파시거래량증가(배)"] is None


def test_pullback_detects_recent_breakout_near_support_after_three_week_limit(monkeypatch):
    install_fake_indicators(monkeypatch)
    df = make_weekly(close=96.0)
    df.loc[df.index[-8], "Close"] = 99.0
    df.loc[df.index[-7], "Close"] = 103.0
    for idx in df.index[-6:-1]:
        df.loc[idx, "Close"] = 101.0

    hit, detail = gogo2.check_conditions(df, candle_cloud_lookback=8, ma_cloud_lookback=4, gc_lookback=4)

    assert hit is True
    assert detail["scan_type"] == "pullback"
    assert detail["캔들구름돌파_N주전"] == 5


def test_result_columns_include_scanner_metadata():
    for column in [
        "scan_type",
        "score",
        "거래량4주비율",
        "거래량20주비율",
        "이격도_구름상단_pct",
        "전환선_기준선",
        "MA배열",
        "구름두께_pct",
    ]:
        assert column in gogo2.RESULT_COLS
