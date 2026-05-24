"""Shared weekly resampling and technical indicator helpers.

This module is the single source for indicator definitions used by pick.py and
the backtest engine. Indicator function bodies were moved from pick.py without
behavior changes.
"""
from __future__ import annotations

import pandas as pd


def add_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    df["ma20"]  = df["close"].rolling(20).mean().round(0)
    df["ma60"]  = df["close"].rolling(60).mean().round(0)
    df["ma120"] = df["close"].rolling(120).mean().round(0)
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

    df["atr14"] = true_range.rolling(14).mean().round(0)
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
    low  = df["low"]

    # ?꾪솚??(9二?
    df["ichi_conv"]  = ((high.rolling(9).max()  + low.rolling(9).min())  / 2).round(0)
    # 湲곗???(26二?
    df["ichi_base"]  = ((high.rolling(26).max() + low.rolling(26).min()) / 2).round(0)
    # ?좏뻾?ㅽ뙩A = (?꾪솚+湲곗?)/2, 26二??욎뿉 湲곕줉
    lead1 = ((df["ichi_conv"] + df["ichi_base"]) / 2).round(0)
    df["ichi_lead1"] = lead1.shift(26)
    # ?좏뻾?ㅽ뙩B = 52二?怨좎? 以묎컙媛? 26二??욎뿉 湲곕줉
    lead2 = ((high.rolling(52).max() + low.rolling(52).min()) / 2).round(0)
    df["ichi_lead2"] = lead2.shift(26)
    # ?꾪뻾?ㅽ뙩 = ?꾩옱 醫낃?, 26二??ㅼ뿉 湲곕줉 (shift(-26))
    df["ichi_lag"]   = df["close"].shift(-26)

    return df


def add_ichimoku_derived_indicators(df: pd.DataFrame) -> pd.DataFrame:
    cloud_spans = df[["ichi_lead1", "ichi_lead2"]]
    df["cloud_top"] = cloud_spans.max(axis=1, skipna=False)
    df["cloud_bottom"] = cloud_spans.min(axis=1, skipna=False)
    df["cloud_thickness"] = (df["cloud_top"] - df["cloud_bottom"]).round(0)

    cloud_top = df["cloud_top"].where(df["cloud_top"] != 0)
    close = df["close"].where(df["close"] != 0)

    df["cloud_thickness_pct"] = ((df["cloud_top"] - df["cloud_bottom"]) / close * 100).round(2)
    df["close_vs_cloud_top_pct"] = ((df["close"] - df["cloud_top"]) / cloud_top * 100).round(2)
    df["conv_base_gap_pct"] = ((df["ichi_conv"] - df["ichi_base"]) / close * 100).round(2)
    return df


def append_future_cloud(df: pd.DataFrame) -> pd.DataFrame:
    """
    ?쇰ぉ ?좏뻾?ㅽ뙩? ?꾩옱 湲곗? +26二?誘몃옒源뚯? 怨꾩궛?⑸땲??
    媛寃??곗씠???놁씠 ichi_lead1/2 留?梨꾩썙吏?誘몃옒 ?됱쓣 異붽??⑸땲??
    """
    high  = df["high"]
    low   = df["low"]
    conv  = df["ichi_conv"]
    base  = df["ichi_base"]

    # 誘몃옒 26二??좎쭨 ?몃뜳??
    last_date = df.index[-1]
    future_dates = pd.date_range(
        start=last_date + pd.offsets.Week(1),
        periods=26,
        freq="W-MON"
    )
    future_df = pd.DataFrame(index=future_dates, columns=df.columns, dtype=float)
    future_df.index.name = "date"

    # ?꾩껜 ?쒕━利?湲곗??쇰줈 ?ш퀎??(?먮낯 df?먯꽌 ?대? shift(26) ?곸슜??
    # 誘몃옒 ?됱뿉???먮낯 留덉?留?26媛?lead1/2 媛믪씠 梨꾩썙?몄빞 ??
    full_high = high
    full_low  = low
    full_conv = conv
    full_base = base

    # 誘몃옒 26二쇱튂 ?좏뻾?ㅽ뙩 raw 媛?(shift 誘몄쟻??
    lead1_raw = ((full_conv + full_base) / 2).round(0)
    lead2_raw = ((full_high.rolling(52).max() + full_low.rolling(52).min()) / 2).round(0)

    tail_lead1 = lead1_raw.iloc[-26:].values
    tail_lead2 = lead2_raw.iloc[-26:].values

    future_df["ichi_lead1"] = tail_lead1
    future_df["ichi_lead2"] = tail_lead2

    combined = pd.concat([df, future_df])
    return combined


INDICATOR_BUILDERS = (
    add_moving_averages,
    add_liquidity_indicators,
    add_volatility_indicators,
    add_momentum_indicators,
    add_signal_indicators,
    add_ichimoku,
    add_ichimoku_derived_indicators,
)


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all weekly indicators in the production order."""
    for builder in INDICATOR_BUILDERS:
        df = builder(df)
    return df


def resample_weekly(df_daily: pd.DataFrame) -> pd.DataFrame:
    """Resample daily OHLCV columns to W-MON weekly OHLCV."""
    df = df_daily.copy()
    df.columns = [c.lower() for c in df.columns]
    df["trading_value"] = df["close"] * df["volume"]
    ohlcv = (
        df.resample("W-MON", label="left", closed="left")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            trading_value=("trading_value", "sum"),
        )
        .dropna(subset=["close"])
    )
    ohlcv.index.name = "date"
    return ohlcv
