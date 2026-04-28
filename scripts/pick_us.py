"""
US weekly stock picker.

Fetches daily data for a US ticker and writes weekly OHLCV data with
MA20/60/120, ATR14, RSI14, MACD, cross/divergence signals, and Ichimoku indicators to CSV.

Usage:
    python scripts/pick_us.py AAPL
    python scripts/pick_us.py NVDA --years 5 --output ./pick_output
"""

import argparse
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

import FinanceDataReader as fdr
import pandas as pd


US_MARKETS = ("NASDAQ", "NYSE", "AMEX")


# ─────────────────────────────────────────
# Indicators
# ─────────────────────────────────────────

def add_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    df["ma20"] = df["close"].rolling(20).mean().round(2)
    df["ma60"] = df["close"].rolling(60).mean().round(2)
    df["ma120"] = df["close"].rolling(120).mean().round(2)
    return df


def add_liquidity_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df["trading_value"] = df["trading_value"].round(0)
    df["volume_ma20"] = df["volume"].rolling(20).mean().round(0)
    df["volume_ratio_20"] = (df["volume"] / df["volume_ma20"].where(df["volume_ma20"] != 0)).round(2)
    return df


def add_volatility_indicators(df: pd.DataFrame) -> pd.DataFrame:
    prev_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    df["atr14"] = true_range.rolling(14).mean().round(2)
    df["atr14_pct"] = (df["atr14"] / df["close"].where(df["close"] != 0) * 100).round(2)
    return df


def add_momentum_indicators(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"]
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    avg_gain = gains.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = losses.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    relative_strength = avg_gain / avg_loss.where(avg_loss != 0)
    rsi = 100 - (100 / (1 + relative_strength))
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100)
    rsi = rsi.mask((avg_loss == 0) & (avg_gain == 0), 50)
    df["rsi14"] = rsi.round(2)

    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    df["macd"] = (ema12 - ema26).round(2)
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False, min_periods=9).mean().round(2)
    df["macd_hist"] = (df["macd"] - df["macd_signal"]).round(2)
    return df


def add_signal_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df["ma20_60_cross"] = _cross_signal(df["ma20"], df["ma60"], "golden", "dead")
    df["ma60_120_cross"] = _cross_signal(df["ma60"], df["ma120"], "golden", "dead")
    df["macd_signal_cross"] = _cross_signal(df["macd"], df["macd_signal"], "bullish", "bearish")
    df["rsi_divergence"] = pd.NA
    df["macd_hist_divergence"] = pd.NA
    df["strict_divergence"] = pd.NA
    _add_divergence_signals(df)
    return df


def _cross_signal(short: pd.Series, long: pd.Series, up_label: str, down_label: str) -> pd.Series:
    signal = pd.Series(pd.NA, index=short.index, dtype="object")
    prev_short = short.shift(1)
    prev_long = long.shift(1)
    valid = short.notna() & long.notna() & prev_short.notna() & prev_long.notna()

    signal.loc[valid & (prev_short <= prev_long) & (short > long)] = up_label
    signal.loc[valid & (prev_short >= prev_long) & (short < long)] = down_label
    return signal


def _add_divergence_signals(df: pd.DataFrame, lookback: int = 52, wing: int = 2) -> None:
    low_swings = _swing_points(df["low"], "low", wing)
    high_swings = _swing_points(df["high"], "high", wing)

    _mark_divergence(df, low_swings, "bullish", lookback)
    _mark_divergence(df, high_swings, "bearish", lookback)


def _swing_points(values: pd.Series, kind: str, wing: int) -> list[int]:
    points: list[int] = []
    for pos in range(wing, len(values) - wing):
        value = values.iloc[pos]
        if pd.isna(value):
            continue

        window = values.iloc[pos - wing : pos + wing + 1]
        if window.isna().any():
            continue

        others = window.drop(window.index[wing])
        if kind == "low" and value < others.min():
            points.append(pos)
        elif kind == "high" and value > others.max():
            points.append(pos)
    return points


def _mark_divergence(df: pd.DataFrame, swing_points: list[int], direction: str, lookback: int) -> None:
    price_col = "low" if direction == "bullish" else "high"
    for current in swing_points:
        previous_candidates = [pos for pos in swing_points if 0 < current - pos <= lookback]
        if not previous_candidates:
            continue

        previous = previous_candidates[-1]
        price_current = df[price_col].iloc[current]
        price_previous = df[price_col].iloc[previous]
        rsi_current = df["rsi14"].iloc[current]
        rsi_previous = df["rsi14"].iloc[previous]
        hist_current = df["macd_hist"].iloc[current]
        hist_previous = df["macd_hist"].iloc[previous]

        values = [price_current, price_previous, rsi_current, rsi_previous, hist_current, hist_previous]
        if any(pd.isna(value) for value in values):
            continue

        if direction == "bullish":
            price_condition = price_current < price_previous
            rsi_condition = rsi_current > rsi_previous
            hist_condition = hist_current > hist_previous
        else:
            price_condition = price_current > price_previous
            rsi_condition = rsi_current < rsi_previous
            hist_condition = hist_current < hist_previous

        if not price_condition:
            continue
        if rsi_condition:
            df.iloc[current, df.columns.get_loc("rsi_divergence")] = direction
        if hist_condition:
            df.iloc[current, df.columns.get_loc("macd_hist_divergence")] = direction
        if rsi_condition and hist_condition:
            df.iloc[current, df.columns.get_loc("strict_divergence")] = direction


def add_ichimoku(df: pd.DataFrame) -> pd.DataFrame:
    high = df["high"]
    low = df["low"]

    df["ichi_conv"] = ((high.rolling(9).max() + low.rolling(9).min()) / 2).round(2)
    df["ichi_base"] = ((high.rolling(26).max() + low.rolling(26).min()) / 2).round(2)
    lead1 = ((df["ichi_conv"] + df["ichi_base"]) / 2).round(2)
    df["ichi_lead1"] = lead1.shift(26)
    lead2 = ((high.rolling(52).max() + low.rolling(52).min()) / 2).round(2)
    df["ichi_lead2"] = lead2.shift(26)
    df["ichi_lag"] = df["close"].shift(-26)

    return df


def add_ichimoku_derived_indicators(df: pd.DataFrame) -> pd.DataFrame:
    cloud_spans = df[["ichi_lead1", "ichi_lead2"]]
    df["cloud_top"] = cloud_spans.max(axis=1, skipna=False)
    df["cloud_bottom"] = cloud_spans.min(axis=1, skipna=False)
    df["cloud_thickness"] = (df["cloud_top"] - df["cloud_bottom"]).round(2)

    cloud_top = df["cloud_top"].where(df["cloud_top"] != 0)
    close = df["close"].where(df["close"] != 0)

    df["cloud_thickness_pct"] = ((df["cloud_top"] - df["cloud_bottom"]) / close * 100).round(2)
    df["close_vs_cloud_top_pct"] = ((df["close"] - df["cloud_top"]) / cloud_top * 100).round(2)
    df["conv_base_gap_pct"] = ((df["ichi_conv"] - df["ichi_base"]) / close * 100).round(2)
    return df


# ─────────────────────────────────────────
# Data fetch and weekly resample
# ─────────────────────────────────────────

def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def resolve_stock_name(ticker: str) -> str:
    ticker = normalize_ticker(ticker)
    for market in US_MARKETS:
        try:
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                listing = fdr.StockListing(market)
        except Exception:
            continue

        code_col, name_col = None, None
        for col in listing.columns:
            if col in ("Code", "Symbol", "ticker"):
                code_col = col
            if col in ("Name", "CompanyName", "name"):
                name_col = col

        if not code_col or not name_col:
            continue

        codes = listing[code_col].astype(str).str.upper()
        matched = listing.loc[codes == ticker, name_col]
        if not matched.empty:
            return str(matched.iloc[0]).strip()

    return ""


def sanitize_filename(text: str) -> str:
    return re.sub(r'[<>:"/\\\\|?*]', "_", text).strip()


def fetch_weekly(ticker: str, years: int) -> pd.DataFrame:
    end = datetime.today()
    # MA120 warmup buffer + Ichimoku future span buffer.
    start = end - timedelta(weeks=(years * 52) + 120 + 52)

    print(f"[INFO] {ticker} daily lookup: {start.date()} ~ {end.date()}")
    df_daily = fdr.DataReader(ticker, start=start.strftime("%Y-%m-%d"))

    if df_daily.empty:
        raise ValueError(f"No stock data: {ticker}")

    df_daily.columns = [c.lower() for c in df_daily.columns]
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df_daily.columns)
    if missing:
        raise ValueError(f"Missing required columns for {ticker}: {', '.join(sorted(missing))}")

    df_daily["trading_value"] = df_daily["close"] * df_daily["volume"]

    # US weekly candles are labeled by Friday. Exclude the current incomplete
    # week when the latest daily bar is earlier than that Friday label.
    ohlcv = df_daily.resample("W-FRI").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        trading_value=("trading_value", "sum"),
    ).dropna(subset=["close"])
    ohlcv = ohlcv[ohlcv.index <= df_daily.index.max()]

    ohlcv.index.name = "date"
    return ohlcv


# ─────────────────────────────────────────
# Future cloud rows
# ─────────────────────────────────────────

def append_future_cloud(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ichimoku leading spans are projected 26 weeks forward.
    Future rows contain only ichi_lead1/2 values and no price data.
    """
    high = df["high"]
    low = df["low"]
    conv = df["ichi_conv"]
    base = df["ichi_base"]

    last_date = df.index[-1]
    future_dates = pd.date_range(
        start=last_date + pd.offsets.Week(1),
        periods=26,
        freq="W-FRI",
    )
    future_df = pd.DataFrame(index=future_dates, columns=df.columns, dtype=float)
    future_df.index.name = "date"

    lead1_raw = ((conv + base) / 2).round(2)
    lead2_raw = ((high.rolling(52).max() + low.rolling(52).min()) / 2).round(2)

    future_df["ichi_lead1"] = lead1_raw.iloc[-26:].values
    future_df["ichi_lead2"] = lead2_raw.iloc[-26:].values

    return pd.concat([df, future_df])


# ─────────────────────────────────────────
# Output range filtering
# ─────────────────────────────────────────

def trim_to_years(df: pd.DataFrame, years: int) -> pd.DataFrame:
    cutoff = datetime.today() - timedelta(weeks=years * 52)
    mask = (df.index >= cutoff) | df["open"].isna()
    return df[mask]


# ─────────────────────────────────────────
# CSV output
# ─────────────────────────────────────────

def save_csv(df: pd.DataFrame, ticker: str, stock_name: str, output_dir: str) -> Path:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    today_str = datetime.today().strftime("%Y%m%d")
    safe_ticker = sanitize_filename(ticker)
    safe_name = sanitize_filename(stock_name)
    if safe_name:
        filename = Path(output_dir) / f"{safe_ticker}_{safe_name}_weekly_{today_str}.csv"
    else:
        filename = Path(output_dir) / f"{safe_ticker}_weekly_{today_str}.csv"

    df = df.copy()
    df.insert(0, "ticker", ticker)
    df.insert(1, "name", stock_name)
    cols = [
        "ticker", "name",
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
    df = df.reindex(columns=cols)

    price_cols = [
        "open", "high", "low", "close",
        "ma20", "ma60", "ma120",
        "atr14", "macd", "macd_signal", "macd_hist",
        "ichi_conv", "ichi_base", "ichi_lead1", "ichi_lead2", "ichi_lag",
        "cloud_top", "cloud_bottom", "cloud_thickness",
    ]
    integer_cols = ["volume", "trading_value", "volume_ma20"]
    ratio_cols = [
        "volume_ratio_20", "atr14_pct", "rsi14",
        "cloud_thickness_pct", "close_vs_cloud_top_pct", "conv_base_gap_pct",
    ]
    for col in price_cols:
        df[col] = df[col].round(2)
    for col in integer_cols:
        df[col] = df[col].round(0).astype("Int64")
    for col in ratio_cols:
        df[col] = df[col].round(2)
    df.index = df.index.strftime("%Y-%m-%d")

    df.to_csv(filename, encoding="utf-8-sig")
    return filename


# ─────────────────────────────────────────
# Summary output
# ─────────────────────────────────────────

def print_summary(df: pd.DataFrame, ticker: str, stock_name: str, filepath: Path) -> None:
    price_rows = df[df["open"].notna()]
    future_rows = df[df["open"].isna()]

    print()
    print("=" * 50)
    print(f"  Ticker      : {ticker}")
    print(f"  Name        : {stock_name or '-'}")
    print(f"  Price data  : {price_rows.index[0]} ~ {price_rows.index[-1]}")
    print(f"  Rows        : {len(price_rows)} weeks (price) + {len(future_rows)} weeks (future cloud)")
    print()

    last = price_rows.iloc[-1]
    print("  [Latest weekly candle]")
    print(f"    Close     : {last['close']:,.2f}")
    print(f"    MA20      : {last['ma20']:,.2f}" if pd.notna(last["ma20"]) else "    MA20      : -")
    print(f"    MA60      : {last['ma60']:,.2f}" if pd.notna(last["ma60"]) else "    MA60      : -")
    print(f"    MA120     : {last['ma120']:,.2f}" if pd.notna(last["ma120"]) else "    MA120     : -")
    print(f"    ATR14     : {last['atr14']:,.2f}" if pd.notna(last["atr14"]) else "    ATR14     : -")
    print(f"    RSI14     : {last['rsi14']:,.2f}" if pd.notna(last["rsi14"]) else "    RSI14     : -")
    print(f"    MACD      : {last['macd']:,.2f}" if pd.notna(last["macd"]) else "    MACD      : -")
    print(f"    Conv line : {last['ichi_conv']:,.2f}" if pd.notna(last["ichi_conv"]) else "    Conv line : -")
    print(f"    Base line : {last['ichi_base']:,.2f}" if pd.notna(last["ichi_base"]) else "    Base line : -")
    print()
    print(f"  Saved path  : {filepath}")
    print("=" * 50)


# ─────────────────────────────────────────
# Callable entry point
# ─────────────────────────────────────────

def run_pick_us(
    ticker: str,
    years: int = 5,
    output_dir: str = "./output",
    no_future_cloud: bool = False,
    stock_name: str | None = None,
) -> None:
    ticker = normalize_ticker(ticker)

    if not stock_name:
        stock_name = resolve_stock_name(ticker)

    df = fetch_weekly(ticker, years)
    df = add_moving_averages(df)
    df = add_liquidity_indicators(df)
    df = add_volatility_indicators(df)
    df = add_momentum_indicators(df)
    df = add_signal_indicators(df)
    df = add_ichimoku(df)
    df = add_ichimoku_derived_indicators(df)

    if not no_future_cloud:
        df = append_future_cloud(df)
        df = add_ichimoku_derived_indicators(df)

    df = trim_to_years(df, years)
    filepath = save_csv(df, ticker, stock_name, output_dir)
    print_summary(df, ticker, stock_name, filepath)


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="US weekly stock CSV exporter")
    parser.add_argument("ticker", help="US ticker symbol (e.g. AAPL, MSFT, NVDA)")
    parser.add_argument("--years", type=int, default=5, help="Lookup period in years (default: 5)")
    parser.add_argument("--output", default="./output", help="Output directory (default: ./output)")
    parser.add_argument("--no-future-cloud", action="store_true", help="Exclude future cloud rows")
    args = parser.parse_args()

    try:
        run_pick_us(
            ticker=args.ticker,
            years=args.years,
            output_dir=args.output,
            no_future_cloud=args.no_future_cloud,
        )
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
