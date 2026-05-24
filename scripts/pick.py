"""
weekly_stock.py
종목코드를 입력받아 3년치 주봉 데이터를 CSV로 추출합니다.
포함 지표: MA20/60/120, ATR14, RSI14, MACD, 교차/다이버전스 신호, 일목균형표 (전환/기준/선행A,B/후행)

사용법:
    python pick.py 005930
    python pick.py 005930 --years 3 --output ./output
"""

import argparse
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import FinanceDataReader as fdr
import pandas as pd

KOREAN_MARKETS = ("KOSPI", "KOSDAQ")

try:
    from fdr_timeout import (
        DEFAULT_FETCH_RETRIES,
        DEFAULT_REQUEST_TIMEOUT,
        fetch_with_retries,
        install_default_timeout,
    )
except ModuleNotFoundError:
    from scripts.fdr_timeout import (
        DEFAULT_FETCH_RETRIES,
        DEFAULT_REQUEST_TIMEOUT,
        fetch_with_retries,
        install_default_timeout,
    )

try:
    from weekly_indicators import (
        _add_divergence_signals,
        _cross_signal,
        _mark_divergence,
        _swing_points,
        add_all_indicators,
        add_ichimoku,
        add_ichimoku_derived_indicators,
        add_liquidity_indicators,
        add_momentum_indicators,
        add_moving_averages,
        add_signal_indicators,
        add_volatility_indicators,
        append_future_cloud,
        resample_weekly,
    )
except ModuleNotFoundError:
    from scripts.weekly_indicators import (  # type: ignore
        _add_divergence_signals,
        _cross_signal,
        _mark_divergence,
        _swing_points,
        add_all_indicators,
        add_ichimoku,
        add_ichimoku_derived_indicators,
        add_liquidity_indicators,
        add_momentum_indicators,
        add_moving_averages,
        add_signal_indicators,
        add_volatility_indicators,
        append_future_cloud,
        resample_weekly,
    )


# ─────────────────────────────────────────

def resolve_stock_metadata(ticker: str) -> tuple[str, str]:
    ticker = ticker.strip().zfill(6)

    for market in KOREAN_MARKETS:
        try:
            def load_listing() -> pd.DataFrame:
                result = fdr.StockListing(market)
                if not isinstance(result, pd.DataFrame) or result.empty:
                    raise ValueError(f"Invalid StockListing response for {market}")
                columns = set(result.columns)
                if (
                    not columns.intersection({"Code", "Symbol", "ticker"})
                    or not columns.intersection({"Name", "CompanyName", "name"})
                ):
                    raise ValueError(f"StockListing response missing ticker/name columns for {market}")
                return result

            listing = fetch_with_retries(load_listing)
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

        codes = listing[code_col].astype(str).str.zfill(6)
        matched = listing.loc[codes == ticker, name_col]
        if not matched.empty:
            return str(matched.iloc[0]).strip(), market

    return "", ""


def resolve_stock_name(ticker: str) -> str:
    stock_name, _ = resolve_stock_metadata(ticker)
    return stock_name


def resolve_stock_market(ticker: str) -> str:
    _, market = resolve_stock_metadata(ticker)
    return market


def sanitize_filename(text: str) -> str:
    return re.sub(r'[<>:"/\\\\|?*]', "_", text).strip()


def normalize_market(market: str | None) -> str:
    if not market:
        return ""
    market_text = str(market).strip().upper()
    if not market_text or market_text == "NAN":
        return ""
    return sanitize_filename(market_text)


def cleanup_old_weekly_csvs(output_dir: Path, ticker: str, today_str: str) -> None:
    weekly_pattern = re.compile(r"^(?P<body>.+)_weekly_(?P<date>\d{8})\.csv$")
    today = datetime.strptime(today_str, "%Y%m%d").date()

    for path in output_dir.glob("*_weekly_*.csv"):
        if not path.is_file():
            continue

        match = weekly_pattern.match(path.name)
        if not match:
            continue

        body_parts = match.group("body").split("_")
        file_ticker = body_parts[1] if body_parts[0].upper() in KOREAN_MARKETS and len(body_parts) > 1 else body_parts[0]
        if file_ticker != ticker:
            continue

        try:
            file_date = datetime.strptime(match.group("date"), "%Y%m%d").date()
        except ValueError:
            continue

        if file_date >= today:
            continue

        try:
            path.unlink()
            print(f"[INFO] old weekly CSV removed: {path}")
        except OSError as exc:
            print(f"[WARN] old weekly CSV remove failed: {path} ({exc})", file=sys.stderr)


def fetch_weekly(
    ticker: str,
    years: int,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    fetch_retries: int = DEFAULT_FETCH_RETRIES,
) -> pd.DataFrame:
    install_default_timeout(request_timeout)

    end   = datetime.today()
    # MA120 워밍업 버퍼 + 일목 선행 26주 버퍼를 넉넉히 포함
    # 120주 ≈ 2.3년, 거기에 years 추가, 선행스팬 미래 행은 별도 처리
    start = end - timedelta(weeks=(years * 52) + 120 + 52)

    print(f"[INFO] {ticker} 일봉 조회: {start.date()} ~ {end.date()}")
    df_daily = fetch_with_retries(
        lambda: fdr.DataReader(ticker, start=start.strftime("%Y-%m-%d")),
        retries=fetch_retries,
    )

    if df_daily.empty:
        raise ValueError(f"종목 데이터 없음: {ticker}")

    ohlcv = resample_weekly(df_daily)
    return ohlcv


# ─────────────────────────────────────────

def trim_to_years(df: pd.DataFrame, years: int) -> pd.DataFrame:
    cutoff = datetime.today() - timedelta(weeks=years * 52)
    # 미래 행(가격 없음)은 유지
    mask = (df.index >= cutoff) | df["open"].isna()
    return df[mask]


# ─────────────────────────────────────────
# CSV 저장
# ─────────────────────────────────────────

def save_csv(df: pd.DataFrame, ticker: str, stock_name: str, output_dir: str, market: str | None = None) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    today_str = datetime.today().strftime("%Y%m%d")
    safe_ticker = sanitize_filename(ticker)
    safe_market = normalize_market(market)
    safe_name = sanitize_filename(stock_name)
    filename_parts = [safe_ticker]
    if safe_market:
        filename_parts = [safe_market, safe_ticker]
    if safe_name:
        filename_parts.append(safe_name)

    if len(filename_parts) > 1:
        filename = output_path / f"{'_'.join(filename_parts)}_weekly_{today_str}.csv"
    else:
        filename = output_path / f"{safe_ticker}_weekly_{today_str}.csv"

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
        "ma20_60_cross", "ma60_120_cross", "macd_signal_cross",
        "rsi_divergence", "macd_hist_divergence", "strict_divergence",
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
    cleanup_old_weekly_csvs(output_path, ticker, today_str)
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

def run_pick(
    ticker: str,
    years: int = 3,
    output_dir: str = "./output",
    no_future_cloud: bool = False,
    stock_name: str = None,
    market: str | None = None,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    fetch_retries: int = DEFAULT_FETCH_RETRIES,
):
    install_default_timeout(request_timeout)

    ticker = ticker.strip().zfill(6)
    
    # 외부에서 종목명을 넘겨주지 않은 경우에만 조회 (속도 향상)
    if not stock_name or not market:
        resolved_name, resolved_market = resolve_stock_metadata(ticker)
        if not stock_name:
            stock_name = resolved_name
        if not market:
            market = resolved_market
        
    df = fetch_weekly(
        ticker,
        years,
        request_timeout=request_timeout,
        fetch_retries=fetch_retries,
    )
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
    filepath = save_csv(df, ticker, stock_name, output_dir, market=market)
    print_summary(df, ticker, stock_name, filepath)


# ─────────────────────────────────────────
# 메인 (터미널에서 직접 실행할 때)
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="주봉 데이터 CSV 추출기")
    parser.add_argument("ticker",              help="종목코드 (예: 005930)")
    parser.add_argument("--years",   type=int, default=3,        help="조회 기간 (기본: 3년)")
    parser.add_argument("--output",            default="./output", help="출력 디렉토리 (기본: ./output)")
    parser.add_argument("--no-future-cloud",   action="store_true", help="미래 구름 행 제외")
    parser.add_argument("--market",            default=None, help="Market label for filename (e.g. KOSPI, KOSDAQ)")
    parser.add_argument("--request-timeout", type=int, default=DEFAULT_REQUEST_TIMEOUT,
                        help=f"외부 데이터 요청 timeout 초 (기본: {DEFAULT_REQUEST_TIMEOUT})")
    parser.add_argument("--retries", type=int, default=DEFAULT_FETCH_RETRIES,
                        help=f"외부 데이터 조회 실패 시 재시도 횟수 (기본: {DEFAULT_FETCH_RETRIES})")
    args = parser.parse_args()

    try:
        run_pick(
            ticker=args.ticker, 
            years=args.years, 
            output_dir=args.output, 
            no_future_cloud=args.no_future_cloud,
            market=args.market,
            request_timeout=args.request_timeout,
            fetch_retries=args.retries,
        )
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] 예상치 못한 오류: {e}", file=sys.stderr)
        raise

if __name__ == "__main__":
    main()
