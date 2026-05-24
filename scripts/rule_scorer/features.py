"""Extract decision features from a pick_output weekly CSV."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


PRICE_COLUMNS = ("open", "high", "low", "close")
DIVERGENCE_WING = 2


@dataclass(slots=True)
class Features:
    ticker: str
    name: str
    asof_date: str
    close: float
    ma20: float | None
    ma60: float | None
    ma120: float | None
    atr14: float | None
    atr14_pct: float | None
    rsi14: float | None
    macd_hist: float | None
    macd_hist_prev: float | None
    macd_hist_prev2: float | None
    volume_ratio_20: float | None
    ichi_conv: float | None
    ichi_base: float | None
    cloud_top: float | None
    cloud_bottom: float | None
    strict_divergence: str | None
    ma20_60_cross_recent: str | None
    future_cloud_direction: str | None  # "상승운" | "하락운" | "전환 예정" | None
    high_12w: float | None
    high_52w: float | None
    lag_above_price: bool | None
    price_rows: pd.DataFrame
    future_rows: pd.DataFrame


def load_csv(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    return df


def split_price_and_future(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    has_close = df["close"].notna()
    price = df.loc[has_close].copy()
    future = df.loc[~has_close].copy()
    return price, future


def _f(value) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    return float(value)


def _s(value) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text or None


def _ma20_60_cross_recent(price: pd.DataFrame, weeks: int = 4) -> str | None:
    series = price["ma20_60_cross"].tail(weeks)
    for value in reversed(series.tolist()):
        text = _s(value)
        if text in ("golden", "dead"):
            return text
    return None


def _future_cloud_direction(future: pd.DataFrame) -> str | None:
    if future.empty:
        return None

    lead1 = future["ichi_lead1"]
    lead2 = future["ichi_lead2"]
    valid = lead1.notna() & lead2.notna()
    if not valid.any():
        return None

    diff = (lead1[valid] - lead2[valid])
    if (diff > 0).all():
        return "상승운"
    if (diff < 0).all():
        return "하락운"
    return "전환 예정"


def _lag_above_price(price: pd.DataFrame) -> bool | None:
    """후행스팬 = close(t) plotted at row (t-26). True if close(t) > close(t-26)."""
    if len(price) < 27:
        return None
    last_close = _f(price["close"].iloc[-1])
    prev_close = _f(price["close"].iloc[-27])
    if last_close is None or prev_close is None:
        return None
    return last_close > prev_close


def _apply_confirmation_shift(df: pd.DataFrame, wing: int = DIVERGENCE_WING) -> pd.DataFrame:
    """Shift divergence flags to the row where the swing is confirmed."""
    if df.attrs.get("_div_shifted"):
        return df
    out = df.copy()
    for col in ("strict_divergence", "rsi_divergence", "macd_hist_divergence"):
        if col in out.columns:
            out[col] = out[col].shift(wing)
    out.attrs["_div_shifted"] = True
    return out


def extract_features_asof(df: pd.DataFrame, i: int) -> Features:
    """Build Features as of price-row index i without using later price rows."""
    df = _apply_confirmation_shift(df)
    price_all, _future_all = split_price_and_future(df)
    if price_all.empty:
        raise ValueError("CSV has no price rows")
    if i < 0 or i >= len(price_all):
        raise IndexError(f"as-of index {i} out of range (price rows={len(price_all)})")

    price = price_all.iloc[: i + 1]
    if price.empty:
        raise ValueError("CSV has no price rows")

    last = price.iloc[-1]
    future = df.iloc[i + 1 : i + 27]
    ticker = str(last["ticker"]).strip()
    name = str(last["name"]).strip() if pd.notna(last["name"]) else ticker
    asof = str(last["date"]).strip()

    macd_hist = _f(last.get("macd_hist"))
    macd_hist_prev = _f(price["macd_hist"].iloc[-2]) if len(price) >= 2 else None
    macd_hist_prev2 = _f(price["macd_hist"].iloc[-3]) if len(price) >= 3 else None

    high_12w = _f(price["high"].tail(12).max()) if len(price) >= 1 else None
    high_52w = _f(price["high"].tail(52).max()) if len(price) >= 1 else None

    return Features(
        ticker=ticker,
        name=name,
        asof_date=asof,
        close=_f(last["close"]) or 0.0,
        ma20=_f(last.get("ma20")),
        ma60=_f(last.get("ma60")),
        ma120=_f(last.get("ma120")),
        atr14=_f(last.get("atr14")),
        atr14_pct=_f(last.get("atr14_pct")),
        rsi14=_f(last.get("rsi14")),
        macd_hist=macd_hist,
        macd_hist_prev=macd_hist_prev,
        macd_hist_prev2=macd_hist_prev2,
        volume_ratio_20=_f(last.get("volume_ratio_20")),
        ichi_conv=_f(last.get("ichi_conv")),
        ichi_base=_f(last.get("ichi_base")),
        cloud_top=_f(last.get("cloud_top")),
        cloud_bottom=_f(last.get("cloud_bottom")),
        strict_divergence=_s(last.get("strict_divergence")),
        ma20_60_cross_recent=_ma20_60_cross_recent(price),
        future_cloud_direction=_future_cloud_direction(future),
        high_12w=high_12w,
        high_52w=high_52w,
        lag_above_price=_lag_above_price(price),
        price_rows=price,
        future_rows=future,
    )


def extract_features(df: pd.DataFrame) -> Features:
    price, _future = split_price_and_future(df)
    if price.empty:
        raise ValueError("CSV has no price rows")
    return extract_features_asof(df, len(price) - 1)
