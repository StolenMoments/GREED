"""
weekly_stock.py
종목코드를 입력받아 5년치 주봉 데이터를 CSV로 추출합니다.
포함 지표: MA20/60/120, ATR14, RSI14, MACD, 일목균형표 (전환/기준/선행A,B/후행)

사용법:
    python pick.py 005930
    python pick.py 005930 --years 5 --output ./output
"""

import argparse
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import FinanceDataReader as fdr
import pandas as pd


# ─────────────────────────────────────────
# 지표 계산
# ─────────────────────────────────────────

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


def add_ichimoku(df: pd.DataFrame) -> pd.DataFrame:
    high = df["high"]
    low  = df["low"]

    # 전환선 (9주)
    df["ichi_conv"]  = ((high.rolling(9).max()  + low.rolling(9).min())  / 2).round(0)
    # 기준선 (26주)
    df["ichi_base"]  = ((high.rolling(26).max() + low.rolling(26).min()) / 2).round(0)
    # 선행스팬A = (전환+기준)/2, 26주 앞에 기록
    lead1 = ((df["ichi_conv"] + df["ichi_base"]) / 2).round(0)
    df["ichi_lead1"] = lead1.shift(26)
    # 선행스팬B = 52주 고저 중간값, 26주 앞에 기록
    lead2 = ((high.rolling(52).max() + low.rolling(52).min()) / 2).round(0)
    df["ichi_lead2"] = lead2.shift(26)
    # 후행스팬 = 현재 종가, 26주 뒤에 기록 (shift(-26))
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


# ─────────────────────────────────────────
# 데이터 수집 및 리샘플
# ─────────────────────────────────────────

def resolve_stock_name(ticker: str) -> str:
    try:
        listing = fdr.StockListing("KRX")
    except Exception:
        return ""

    code_col, name_col = None, None
    for col in listing.columns:
        if col in ("Code", "Symbol", "ticker"):
            code_col = col
        if col in ("Name", "CompanyName", "name"):
            name_col = col

    if not code_col or not name_col:
        return ""

    listing[code_col] = listing[code_col].astype(str).str.zfill(6)
    matched = listing.loc[listing[code_col] == ticker, name_col]
    if matched.empty:
        return ""

    return str(matched.iloc[0]).strip()


def sanitize_filename(text: str) -> str:
    return re.sub(r'[<>:"/\\\\|?*]', "_", text).strip()

def fetch_weekly(ticker: str, years: int) -> pd.DataFrame:
    end   = datetime.today()
    # MA120 워밍업 버퍼 + 일목 선행 26주 버퍼를 넉넉히 포함
    # 120주 ≈ 2.3년, 거기에 years 추가, 선행스팬 미래 행은 별도 처리
    start = end - timedelta(weeks=(years * 52) + 120 + 52)

    print(f"[INFO] {ticker} 일봉 조회: {start.date()} ~ {end.date()}")
    df_daily = fdr.DataReader(ticker, start=start.strftime("%Y-%m-%d"))

    if df_daily.empty:
        raise ValueError(f"종목 데이터 없음: {ticker}")

    # 컬럼명 소문자 정규화
    df_daily.columns = [c.lower() for c in df_daily.columns]
    df_daily["trading_value"] = df_daily["close"] * df_daily["volume"]

    # 주봉 리샘플 (월요일 기준, 마지막 영업일 기준으로 close)
    ohlcv = df_daily.resample("W-MON", label="left", closed="left").agg(
        open=("open",   "first"),
        high=("high",   "max"),
        low=("low",     "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        trading_value=("trading_value", "sum"),
    ).dropna(subset=["close"])

    ohlcv.index.name = "date"
    return ohlcv


# ─────────────────────────────────────────
# 선행스팬 미래 행 추가
# ─────────────────────────────────────────

def append_future_cloud(df: pd.DataFrame) -> pd.DataFrame:
    """
    일목 선행스팬은 현재 기준 +26주 미래까지 계산됩니다.
    가격 데이터 없이 ichi_lead1/2 만 채워진 미래 행을 추가합니다.
    """
    high  = df["high"]
    low   = df["low"]
    conv  = df["ichi_conv"]
    base  = df["ichi_base"]

    # 미래 26주 날짜 인덱스
    last_date = df.index[-1]
    future_dates = pd.date_range(
        start=last_date + pd.offsets.Week(1),
        periods=26,
        freq="W-MON"
    )
    future_df = pd.DataFrame(index=future_dates, columns=df.columns, dtype=float)
    future_df.index.name = "date"

    # 전체 시리즈 기준으로 재계산 (원본 df에서 이미 shift(26) 적용됨)
    # 미래 행에는 원본 마지막 26개 lead1/2 값이 채워져야 함
    full_high = high
    full_low  = low
    full_conv = conv
    full_base = base

    # 미래 26주치 선행스팬 raw 값 (shift 미적용)
    lead1_raw = ((full_conv + full_base) / 2).round(0)
    lead2_raw = ((full_high.rolling(52).max() + full_low.rolling(52).min()) / 2).round(0)

    tail_lead1 = lead1_raw.iloc[-26:].values
    tail_lead2 = lead2_raw.iloc[-26:].values

    future_df["ichi_lead1"] = tail_lead1
    future_df["ichi_lead2"] = tail_lead2

    combined = pd.concat([df, future_df])
    return combined


# ─────────────────────────────────────────
# 출력 범위 필터링 (요청 기간만)
# ─────────────────────────────────────────

def trim_to_years(df: pd.DataFrame, years: int) -> pd.DataFrame:
    cutoff = datetime.today() - timedelta(weeks=years * 52)
    # 미래 행(가격 없음)은 유지
    mask = (df.index >= cutoff) | df["open"].isna()
    return df[mask]


# ─────────────────────────────────────────
# CSV 저장
# ─────────────────────────────────────────

def save_csv(df: pd.DataFrame, ticker: str, stock_name: str, output_dir: str) -> Path:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    today_str = datetime.today().strftime("%Y%m%d")
    safe_name = sanitize_filename(stock_name)
    if safe_name:
        filename = Path(output_dir) / f"{ticker}_{safe_name}_weekly_{today_str}.csv"
    else:
        filename = Path(output_dir) / f"{ticker}_weekly_{today_str}.csv"

    # 컬럼 순서 정렬
    df = df.copy()
    df.insert(0, "ticker", ticker)
    df.insert(1, "name", stock_name)
    cols = [
        "ticker", "name",
        "open", "high", "low", "close", "volume",
        "trading_value", "volume_ma20", "volume_ratio_20",
        "ma20", "ma60", "ma120",
        "atr14", "atr14_pct", "rsi14", "macd", "macd_signal", "macd_hist",
        "ichi_conv", "ichi_base", "ichi_lead1", "ichi_lead2", "ichi_lag",
        "cloud_top", "cloud_bottom", "cloud_thickness",
        "cloud_thickness_pct", "close_vs_cloud_top_pct", "conv_base_gap_pct",
    ]
    df = df.reindex(columns=cols)
    integer_cols = [
        "open", "high", "low", "close", "volume",
        "trading_value", "volume_ma20",
        "ma20", "ma60", "ma120",
        "atr14",
        "ichi_conv", "ichi_base", "ichi_lead1", "ichi_lead2", "ichi_lag",
        "cloud_top", "cloud_bottom", "cloud_thickness",
    ]
    ratio_cols = [
        "volume_ratio_20", "atr14_pct", "rsi14", "macd", "macd_signal", "macd_hist",
        "cloud_thickness_pct", "close_vs_cloud_top_pct", "conv_base_gap_pct",
    ]
    for col in integer_cols:
        df[col] = df[col].round(0).astype("Int64")
    for col in ratio_cols:
        df[col] = df[col].round(2)
    df.index = df.index.strftime("%Y-%m-%d")

    df.to_csv(filename, encoding="utf-8-sig")
    return filename


# ─────────────────────────────────────────
# 요약 출력
# ─────────────────────────────────────────

def print_summary(df: pd.DataFrame, ticker: str, stock_name: str, filepath: Path):
    price_rows  = df[df["open"].notna()]
    future_rows = df[df["open"].isna()]

    print()
    print("=" * 50)
    print(f"  종목코드  : {ticker}")
    print(f"  종목명    : {stock_name or '-'}")
    print(f"  가격 데이터: {price_rows.index[0]} ~ {price_rows.index[-1]}")
    print(f"  전체 행수  : {len(price_rows)}주 (가격) + {len(future_rows)}주 (미래 구름)")
    print()

    last = price_rows.iloc[-1]
    print(f"  [최근 주봉]")
    print(f"    종가    : {last['close']:,.0f}")
    print(f"    MA20    : {last['ma20']:,.0f}" if pd.notna(last["ma20"])  else "    MA20    : -")
    print(f"    MA60    : {last['ma60']:,.0f}" if pd.notna(last["ma60"])  else "    MA60    : -")
    print(f"    MA120   : {last['ma120']:,.0f}" if pd.notna(last["ma120"]) else "    MA120   : -")
    print(f"    ATR14   : {last['atr14']:,.0f}" if pd.notna(last["atr14"]) else "    ATR14   : -")
    print(f"    RSI14   : {last['rsi14']:,.2f}" if pd.notna(last["rsi14"]) else "    RSI14   : -")
    print(f"    MACD    : {last['macd']:,.2f}" if pd.notna(last["macd"]) else "    MACD    : -")
    print(f"    전환선  : {last['ichi_conv']:,.0f}" if pd.notna(last["ichi_conv"]) else "    전환선  : -")
    print(f"    기준선  : {last['ichi_base']:,.0f}" if pd.notna(last["ichi_base"]) else "    기준선  : -")
    print()
    print(f"  저장 경로  : {filepath}")
    print("=" * 50)


# ─────────────────────────────────────────
# 모듈 호출용 함수 (gogo2.py 등에서 사용)
# ─────────────────────────────────────────

def run_pick(ticker: str, years: int = 5, output_dir: str = "./output", no_future_cloud: bool = False, stock_name: str = None):
    ticker = ticker.strip().zfill(6)
    
    # 외부에서 종목명을 넘겨주지 않은 경우에만 조회 (속도 향상)
    if not stock_name:
        stock_name = resolve_stock_name(ticker)
        
    df = fetch_weekly(ticker, years)
    df = add_moving_averages(df)
    df = add_liquidity_indicators(df)
    df = add_volatility_indicators(df)
    df = add_momentum_indicators(df)
    df = add_ichimoku(df)
    df = add_ichimoku_derived_indicators(df)

    if not no_future_cloud:
        df = append_future_cloud(df)
        df = add_ichimoku_derived_indicators(df)

    df = trim_to_years(df, years)
    filepath = save_csv(df, ticker, stock_name, output_dir)
    print_summary(df, ticker, stock_name, filepath)


# ─────────────────────────────────────────
# 메인 (터미널에서 직접 실행할 때)
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="주봉 데이터 CSV 추출기")
    parser.add_argument("ticker",              help="종목코드 (예: 005930)")
    parser.add_argument("--years",   type=int, default=5,        help="조회 기간 (기본: 5년)")
    parser.add_argument("--output",            default="./output", help="출력 디렉토리 (기본: ./output)")
    parser.add_argument("--no-future-cloud",   action="store_true", help="미래 구름 행 제외")
    args = parser.parse_args()

    try:
        run_pick(
            ticker=args.ticker, 
            years=args.years, 
            output_dir=args.output, 
            no_future_cloud=args.no_future_cloud
        )
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] 예상치 못한 오류: {e}", file=sys.stderr)
        raise

if __name__ == "__main__":
    main()
