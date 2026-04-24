import pandas as pd
import numpy as np
import FinanceDataReader as fdr
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
import os
import json
import argparse

import pick  # pick.py 모듈 연동

# ────────────────────────────────────────
# 1. 일목균형표 계산
# ────────────────────────────────────────
def ichimoku(df):
    high  = df['High']
    low   = df['Low']
    close = df['Close']

    df['tenkan'] = (high.rolling(9).max()  + low.rolling(9).min())  / 2
    df['kijun']  = (high.rolling(26).max() + low.rolling(26).min()) / 2
    df['span_a'] = ((df['tenkan'] + df['kijun']) / 2).shift(26)
    df['span_b'] = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
    df['chikou'] = close.shift(-26)
    return df

# ────────────────────────────────────────
# 2. 이동평균선 계산
# ────────────────────────────────────────
def moving_averages(df):
    df['ma20']  = df['Close'].rolling(20).mean()
    df['ma60']  = df['Close'].rolling(60).mean()
    df['ma120'] = df['Close'].rolling(120).mean()
    df['volume_ma20'] = df['Volume'].rolling(20).mean()
    return df

def safe_ratio(numerator, denominator):
    if pd.isna(numerator) or pd.isna(denominator) or denominator <= 0:
        return 0.0
    return float(numerator / denominator)

def pct_gap(value, base):
    if pd.isna(value) or pd.isna(base) or base == 0:
        return 0.0
    return float((value - base) / base * 100)

def ma_alignment(row):
    if row['ma20'] > row['ma60'] > row['ma120']:
        return '정배열'
    if row['ma20'] < row['ma60'] < row['ma120']:
        return '역배열'
    return '혼조'

def nearest_support_gap_pct(close, supports):
    valid_supports = [level for level in supports if pd.notna(level) and level > 0]
    if not valid_supports or close <= 0:
        return None
    return min(abs(close - level) / level * 100 for level in valid_supports)

# ────────────────────────────────────────
# 3. 조건 체크
#    AI 분석 후보를 넓게 모으는 스캐너:
#    ① 구름 돌파형 ② 구름 돌파 임박형 ③ 돌파 후 눌림형 ④ 추세 확인형
# ────────────────────────────────────────
def check_conditions(df,
                     candle_cloud_lookback,
                     ma_cloud_lookback,
                     gc_lookback,
                     max_cloud_gap=1.25,
                     candle_max_lookback=3,
                     vol_multiplier=1.5,
                     recent_volume_weeks=4):

    if len(df) < 150:
        return False, {}

    df = df.copy()
    df = ichimoku(df)
    df = moving_averages(df)
    df = df.dropna(subset=['span_a', 'span_b', 'ma20', 'ma60', 'ma120', 'volume_ma20'])

    scan_candle_lookback = max(candle_cloud_lookback, 8)
    scanner_min_score = 7

    if len(df) < scan_candle_lookback + 2:
        return False, {}

    today   = datetime.today().weekday()
    end_idx = -1 if today == 4 else -2
    last    = df.iloc[end_idx]
    prev_last = df.iloc[end_idx - 1]

    if recent_volume_weeks > 0:
        recent_start = end_idx - recent_volume_weeks + 1
        if len(df) + recent_start < 0:
            return False, {}
        recent_slice = df.iloc[recent_start:end_idx + 1] if end_idx != -1 else df.iloc[recent_start:]
        if (recent_slice['Volume'] <= 0).any():
            return False, {}

    current_cloud_top = max(last['span_a'], last['span_b'])
    current_cloud_bot = min(last['span_a'], last['span_b'])
    current_close = last['Close']
    close_vs_cloud_top_pct = pct_gap(current_close, current_cloud_top)
    cloud_thickness_pct = pct_gap(current_cloud_top, current_cloud_bot) if current_close == 0 else (
        (current_cloud_top - current_cloud_bot) / current_close * 100
    )
    current_ma_alignment = ma_alignment(last)
    tenkan_above_kijun = last['tenkan'] > last['kijun']
    ma20_rising = last['ma20'] > prev_last['ma20']
    ma60_rising = last['ma60'] > prev_last['ma60']

    # ── 하드 필터: 단기 추세 회복 필수
    # 역배열 판정에서 ma60/ma120 관계는 제외 — 턴어라운드 초입 허용
    if last['ma20'] < last['ma60']:
        return False, {}
    if current_close < last['ma60']:
        return False, {}

    # ── Step 1: 캔들 구름 돌파 탐색
    candle_break_idx  = None
    candle_break_week = None

    for i in range(scan_candle_lookback - 1, -1, -1):
        idx_cur  = end_idx - i
        idx_prev = idx_cur - 1

        cur  = df.iloc[idx_cur]
        prev = df.iloc[idx_prev]

        cloud_top_cur  = max(cur['span_a'],  cur['span_b'])
        cloud_top_prev = max(prev['span_a'], prev['span_b'])

        if (prev['Close'] <= cloud_top_prev) and (cur['Close'] > cloud_top_cur):
            candle_break_idx  = idx_cur
            candle_break_week = i

    signal_idx = candle_break_idx if candle_break_idx is not None else end_idx
    signal = df.iloc[signal_idx]
    prev_4w_vol_avg = df.iloc[signal_idx - 4 : signal_idx]['Volume'].mean()
    signal_vol_ratio_4w = safe_ratio(signal['Volume'], prev_4w_vol_avg)
    signal_vol_ratio_20 = safe_ratio(signal['Volume'], signal['volume_ma20'])
    breakout_vol_ratio = signal_vol_ratio_4w if candle_break_idx is not None else None

    # ── Step 2: MA/GC 탐색
    event_start = candle_break_idx if candle_break_idx is not None else end_idx
    ma_search_start = max(event_start, end_idx - ma_cloud_lookback + 1)
    gc_search_start = max(event_start, end_idx - gc_lookback + 1)

    ma20_break_week, ma60_break_week, ma120_break_week = None, None, None

    for abs_idx in range(ma_search_start, end_idx + 1):
        prev      = df.iloc[abs_idx - 1]
        cur       = df.iloc[abs_idx]
        weeks_ago = end_idx - abs_idx

        cloud_top_cur  = max(cur['span_a'],  cur['span_b'])
        cloud_top_prev = max(prev['span_a'], prev['span_b'])

        if ma20_break_week is None and (prev['ma20'] <= cloud_top_prev) and (cur['ma20'] > cloud_top_cur):
            ma20_break_week = weeks_ago
        if ma60_break_week is None and (prev['ma60'] <= cloud_top_prev) and (cur['ma60'] > cloud_top_cur):
            ma60_break_week = weeks_ago
        if ma120_break_week is None and (prev['ma120'] <= cloud_top_prev) and (cur['ma120'] > cloud_top_cur):
            ma120_break_week = weeks_ago

    ma_broke_cloud = any([ma20_break_week is not None, ma60_break_week is not None, ma120_break_week is not None])

    hit_gc_60_120, hit_gc_20_60 = False, False
    gc_60_120_week, gc_20_60_week = None, None

    for abs_idx in range(gc_search_start, end_idx + 1):
        prev      = df.iloc[abs_idx - 1]
        cur       = df.iloc[abs_idx]
        weeks_ago = end_idx - abs_idx

        if (prev['ma60'] <= prev['ma120']) and (cur['ma60'] > cur['ma120']):
            hit_gc_60_120, gc_60_120_week = True, weeks_ago
        if (prev['ma20'] <= prev['ma60']) and (cur['ma20'] > cur['ma60']):
            hit_gc_20_60, gc_20_60_week = True, weeks_ago

    gc_hit = hit_gc_60_120 or hit_gc_20_60

    current_above_cloud = current_close >= current_cloud_top
    over_max_gap = current_close > current_cloud_top * max_cloud_gap
    recent_breakout = candle_break_idx is not None and candle_break_week <= scan_candle_lookback
    breakout_type = recent_breakout and current_above_cloud and not over_max_gap

    near_cloud_top = current_cloud_top * 0.95 <= current_close < current_cloud_top
    structure_count = sum([
        tenkan_above_kijun,
        ma20_rising,
        current_close > last['ma20'],
        current_close > current_cloud_bot,
        signal_vol_ratio_20 >= 1.0,
    ])
    pre_breakout_type = near_cloud_top and structure_count >= 3 and tenkan_above_kijun

    support_gap = nearest_support_gap_pct(
        current_close,
        [current_cloud_top, last['ma20'], last['kijun']],
    )
    pullback_type = (
        recent_breakout
        and candle_break_week is not None
        and candle_break_week >= 1
        and support_gap is not None
        and support_gap <= 5
        and current_close >= current_cloud_bot
    )

    score = 0
    if breakout_type:
        score += 3
        score += 2 if candle_break_week <= candle_max_lookback else 1
    elif recent_breakout and current_above_cloud:
        score += 2
    if pre_breakout_type:
        score += 3
    if pullback_type:
        score += 3

    if signal_vol_ratio_4w >= vol_multiplier:
        score += 2
    elif signal_vol_ratio_4w >= 1.2:
        score += 1
    if signal_vol_ratio_20 >= 1.25:
        score += 1
    if tenkan_above_kijun:
        score += 1
    if current_close > last['kijun']:
        score += 1
    if ma20_rising:
        score += 1
    if ma60_rising:
        score += 1
    if last['ma20'] > last['ma60']:
        score += 1
    if current_ma_alignment == '정배열':
        score += 1
    if ma_broke_cloud:
        score += 1
    if gc_hit:
        score += 1
    if 0 <= close_vs_cloud_top_pct <= 12:
        score += 1
    if over_max_gap:
        score -= 2

    scan_type = None
    if pullback_type:
        scan_type = 'pullback'
    elif breakout_type:
        scan_type = 'breakout'
    elif pre_breakout_type:
        scan_type = 'pre_breakout'
    elif score >= scanner_min_score:
        scan_type = 'trend_confirm'

    if scan_type is None:
        return False, {}

    detail = {
        'scan_type':          scan_type,
        'score':              int(max(score, 0)),
        '종가':               int(last['Close']),
        '구름상단':           int(current_cloud_top),
        '구름하단':           int(current_cloud_bot),
        '캔들구름돌파_N주전':  candle_break_week,
        '돌파시거래량증가(배)': round(breakout_vol_ratio, 2) if breakout_vol_ratio is not None else None,
        '거래량4주비율':       round(signal_vol_ratio_4w, 2),
        '거래량20주비율':      round(signal_vol_ratio_20, 2),
        '이격도_구름상단_pct': round(close_vs_cloud_top_pct, 2),
        '전환선_기준선':       '전환선>기준선' if tenkan_above_kijun else '전환선<=기준선',
        'MA배열':             current_ma_alignment,
        '구름두께_pct':        round(cloud_thickness_pct, 2),
        'MA20구름돌파_N주전':  ma20_break_week,
        'MA60구름돌파_N주전':  ma60_break_week,
        'MA120구름돌파_N주전': ma120_break_week,
        'GC_60/120_N주전':    gc_60_120_week,
        'GC_20/60_N주전':     gc_20_60_week,
        'MA20':               int(last['ma20']),
        'MA60':               int(last['ma60']),
        'MA120':              int(last['ma120']),
    }
    return True, detail

# ────────────────────────────────────────
# 4. 일봉 → 주봉 변환
# ────────────────────────────────────────
def to_weekly(df):
    df.index = pd.to_datetime(df.index)
    weekly = df.resample('W').agg({
        'Open':   'first',
        'High':   'max',
        'Low':    'min',
        'Close':  'last',
        'Volume': 'sum'
    }).dropna()
    return weekly

# ────────────────────────────────────────
# 5. 종목 리스트 가져오기
# ────────────────────────────────────────
def get_ticker_list(market, min_marcap_billions=500):
    df = fdr.StockListing(market)

    code_col, name_col = None, None
    for c in df.columns:
        if c in ('Code', 'Symbol', 'ticker'): code_col = c
        if c in ('Name', 'CompanyName', 'name'): name_col = c

    if code_col is None:
        raise ValueError(f"종목코드 컬럼을 찾을 수 없음.")

    is_korean_market = market.upper() in ('KOSPI', 'KOSDAQ', 'KRX')

    if is_korean_market:
        df[code_col] = df[code_col].astype(str).str.zfill(6)
        
        # 1. 시가총액 필터 (Marcap 컬럼이 존재할 경우)
        if 'Marcap' in df.columns:
            # Marcap은 원 단위이므로 500억 = 50,000,000,000
            min_marcap = min_marcap_billions * 100_000_000
            df = df[df['Marcap'] >= min_marcap]

        if name_col:
            # 2. 잡주 필터 (보통주만, 스팩 제외, 리츠 제외)
            is_common = df[code_col].str.endswith('0')
            is_not_spac = ~df[name_col].str.contains('스팩|SPAC|제[0-9]+호', case=False, na=False, regex=True)
            is_not_reits = ~df[name_col].str.contains('리츠|투자회사|맥쿼리인프라|선박투자', na=False, regex=True)
            
            df = df[is_common & is_not_spac & is_not_reits]
    else:
        df[code_col] = df[code_col].astype(str)

    tickers = df[code_col].tolist()
    names   = dict(zip(df[code_col], df[name_col] if name_col else [''] * len(df)))
    
    return tickers, names

# ────────────────────────────────────────
# 6. 진행 상태 저장/로드
# ────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pick_output")
PROGRESS_FILE = os.path.join(OUTPUT_DIR, "screening_progress.json")

def load_progress():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    today = datetime.today().strftime("%Y-%m-%d")
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if data.get('date') == today:
            print(f"[재실행 감지] 오늘({today}) 이미 처리된 종목 {len(data.get('processed', []))}개 스킵")
            return data.get('processed', []), data.get('results', [])
    return [], []

def save_progress(processed_tickers, results, lock):
    today = datetime.today().strftime("%Y-%m-%d")
    with lock:
        data = {
            'date':      today,
            'processed': processed_tickers,
            'results':   results,
        }
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

def clear_progress():
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        print("진행 상태 초기화 완료")

# ────────────────────────────────────────
# 7. 단일 종목 처리 (스레드 작업 단위)
# ────────────────────────────────────────
def process_ticker(ticker, name, market, start, end,
                   candle_cloud_lookback, ma_cloud_lookback, gc_lookback,
                   recent_volume_weeks=4):
    try:
        df = fdr.DataReader(ticker, start, end)

        if df is None or df.empty or 'Close' not in df.columns:
            return ticker, None

        weekly = to_weekly(df)

        if weekly.empty or len(weekly) < 10:
            return ticker, None

        hit, detail = check_conditions(
            weekly,
            candle_cloud_lookback = candle_cloud_lookback,
            ma_cloud_lookback     = ma_cloud_lookback,
            gc_lookback           = gc_lookback,
            recent_volume_weeks   = recent_volume_weeks,
        )

        if hit:
            detail['종목코드'] = ticker
            detail['종목명']   = name
            detail['시장']     = market
            return ticker, detail

    except Exception:
        pass

    return ticker, None

# ────────────────────────────────────────
# 8. 결과 CSV append
# ────────────────────────────────────────
RESULT_COLS = [
    '시장', '종목코드', '종목명', 'scan_type', 'score', '종가',
    '캔들구름돌파_N주전', '돌파시거래량증가(배)', '거래량4주비율', '거래량20주비율',
    '이격도_구름상단_pct', '전환선_기준선', 'MA배열', '구름두께_pct',
    'MA20구름돌파_N주전', 'MA60구름돌파_N주전', 'MA120구름돌파_N주전',
    'GC_60/120_N주전', 'GC_20/60_N주전',
    '구름상단', '구름하단',
    'MA20', 'MA60', 'MA120',
]

def get_result_filename():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return os.path.join(OUTPUT_DIR, f"screening_{datetime.today().strftime('%Y%m%d')}.csv")

def flush_to_csv(batch_hits, filename, lock):
    if not batch_hits:
        return
    df_batch = pd.DataFrame(batch_hits)
    cols     = [c for c in RESULT_COLS if c in df_batch.columns]
    with lock:
        write_header = not os.path.exists(filename)
        df_batch[cols].to_csv(filename, mode='a', index=False,
                              header=write_header, encoding='utf-8-sig')

# ────────────────────────────────────────
# 9. 단일 시장 스크리닝 (멀티스레드)
# ────────────────────────────────────────
def screen_market(market, start, end,
                  candle_cloud_lookback, ma_cloud_lookback, gc_lookback,
                  processed_tickers, all_results,
                  batch_size=50, max_workers=8,
                  file_lock=None, print_lock=None,
                  recent_volume_weeks=4):
    try:
        tickers, names = get_ticker_list(market)
    except Exception as e:
        print(f"  [{market}] 종목 리스트 오류: {e}")
        return

    processed_set = set(processed_tickers)
    remaining     = [t for t in tickers if t not in processed_set]
    skipped       = len(tickers) - len(remaining)

    print(f"\n[{market}] 전체 {len(tickers)}개 | 스킵 {skipped}개 | 처리대상 {len(remaining)}개")
    print(f"  파라미터 → 캔들구름: {candle_cloud_lookback}주 | 이평선구름: {ma_cloud_lookback}주 | GC: {gc_lookback}주")

    result_filename = get_result_filename()
    total           = len(remaining)
    batch_hits      = []
    errors          = []

    for batch_start in range(0, total, batch_size):
        batch_tickers = remaining[batch_start:batch_start + batch_size]
        batch_num     = batch_start // batch_size + 1
        futures_map   = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for ticker in batch_tickers:
                future = executor.submit(
                    process_ticker,
                    ticker, names.get(ticker, ''), market,
                    start, end,
                    candle_cloud_lookback, ma_cloud_lookback, gc_lookback,
                    recent_volume_weeks,
                )
                futures_map[future] = ticker

            for future in as_completed(futures_map):
                ticker, detail = future.result()
                processed_tickers.append(ticker)

                if detail:
                    batch_hits.append(detail)
                    all_results.append(detail)

        # 배치 완료 출력
        end_idx    = min(batch_start + batch_size, total)
        found_this = len(batch_hits)

        with print_lock:
            print(f"\n  [배치 {batch_num}] {end_idx}/{total} 탐색완료 "
                  f"| 이번배치 {found_this}개 발견 | 누적 {len(all_results)}개")

            if batch_hits:
                df_batch = pd.DataFrame(batch_hits)
                cols     = [c for c in RESULT_COLS if c in df_batch.columns]
                print(df_batch[cols].to_string(index=False))

        flush_to_csv(batch_hits, result_filename, file_lock)
        save_progress(processed_tickers, all_results, file_lock)
        batch_hits = []

    if errors:
        print(f"  오류 발생 종목: {len(errors)}개")

# ────────────────────────────────────────
# 10. 시장별 파라미터 결정
# ────────────────────────────────────────
MARKET_DEFAULTS = {
    'KOSPI':  {'candle': 12, 'ma': 6, 'gc': 6},
    'KOSDAQ': {'candle':  8, 'ma': 4, 'gc': 4},
}

def resolve_params(market, candle_override, ma_override, gc_override):
    """
    CLI 인자가 있으면 시장 구분 없이 동일 적용.
    없으면 시장별 기본값 사용.
    """
    defaults = MARKET_DEFAULTS.get(market, {'candle': 8, 'ma': 4, 'gc': 4})
    return (
        candle_override if candle_override is not None else defaults['candle'],
        ma_override     if ma_override     is not None else defaults['ma'],
        gc_override     if gc_override     is not None else defaults['gc'],
    )

# ────────────────────────────────────────
# 11. 전종목 스크리닝 실행
# ────────────────────────────────────────
def screen_all(markets=None,
               candle_override=None,
               ma_override=None,
               gc_override=None,
               weeks_back=160,
               batch_size=50,
               max_workers=8,
               force_restart=False,
               recent_volume_weeks=4):
    if markets is None:
        markets = ['KOSPI', 'KOSDAQ']

    if force_restart:
        clear_progress()

    end   = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(weeks=weeks_back)).strftime("%Y-%m-%d")

    print("=" * 60)
    print(f"조회 기간    : {start} ~ {end}")
    print(f"배치 단위    : {batch_size}개 | 스레드 수: {max_workers}")
    if candle_override or ma_override or gc_override:
        print(f"파라미터 오버라이드 → "
              f"캔들: {candle_override}주 | 이평선: {ma_override}주 | GC: {gc_override}주")
    else:
        print("파라미터     : 시장별 기본값 사용 (KOSPI 12/6/6 | KOSDAQ 8/4/4)")
    print("=" * 60)

    processed_tickers, all_results = load_progress()

    file_lock  = threading.Lock()
    print_lock = threading.Lock()

    for market in markets:
        candle, ma, gc = resolve_params(market, candle_override, ma_override, gc_override)
        screen_market(
            market, start, end,
            candle, ma, gc,
            processed_tickers,
            all_results,
            batch_size          = batch_size,
            max_workers         = max_workers,
            file_lock           = file_lock,
            print_lock          = print_lock,
            recent_volume_weeks = recent_volume_weeks,
        )

    if not all_results:
        print("\n조건 충족 종목 없음")
        return pd.DataFrame()

    df_result = pd.DataFrame(all_results)
    cols      = [c for c in RESULT_COLS if c in df_result.columns]
    sort_cols = [c for c in ['score', '캔들구름돌파_N주전'] if c in df_result.columns]
    ascending = [False if c == 'score' else True for c in sort_cols]
    df_result = df_result[cols].sort_values(sort_cols, ascending=ascending, na_position='last')

    print(f"\n{'='*60}")
    print(f"✅ 스크리닝 완료 | 조건 충족 종목 : {len(df_result)}개")
    print(f"✅ 결과 파일     : {get_result_filename()}")
    print(f"{'='*60}")

    return df_result

# ────────────────────────────────────────
# 12. CLI 파라미터 파싱
# ────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="주봉 일목균형표 + 이동평균선 스크리닝",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
기본 실행 (시장별 기본값):
  python gogo2.py

파라미터 직접 지정 (전 시장 동일 적용):
  python gogo2.py --candle 10 --ma 5 --gc 5

기타 옵션:
  python gogo2.py --workers 10 --restart
        """
    )
    parser.add_argument('--candle',  type=int, default=None,
                        help='캔들 구름 돌파 lookback (주)\n기본: KOSPI=12, KOSDAQ=8')
    parser.add_argument('--ma',      type=int, default=None,
                        help='이평선 구름 돌파 lookback (주)\n기본: KOSPI=6,  KOSDAQ=4')
    parser.add_argument('--gc',      type=int, default=None,
                        help='골든크로스 lookback (주)\n기본: KOSPI=6,  KOSDAQ=4')
    parser.add_argument('--workers', type=int, default=8,
                        help='병렬 스레드 수 (기본: 8)')
    parser.add_argument('--batch',   type=int, default=50,
                        help='배치 단위 (기본: 50)')
    parser.add_argument('--weeks',   type=int, default=160,
                        help='데이터 조회 기간 (주, 기본: 160)')
    parser.add_argument('--restart', action='store_true',
                        help='당일 진행 상태 무시하고 처음부터 재실행')
    parser.add_argument('--recent-vol-weeks', type=int, default=4,
                        help='최근 N 주 모두 volume>0 이어야 통과 (거래정지 필터, 기본 4, 0=비활성)')
    return parser.parse_args()

# ────────────────────────────────────────
# 13. 메인 실행
# ────────────────────────────────────────
if __name__ == "__main__":
    args = parse_args()

    result_df = screen_all(
        markets             = ['KOSPI', 'KOSDAQ'],
        candle_override     = args.candle,
        ma_override         = args.ma,
        gc_override         = args.gc,
        weeks_back          = args.weeks,
        batch_size          = args.batch,
        max_workers         = args.workers,
        force_restart       = args.restart,
        recent_volume_weeks = args.recent_vol_weeks,
    )

    # ==========================================
    # ★ 추가된 부분: 스크리닝 결과 종목들을 pick.py로 추출
    # ==========================================
    if result_df is not None and not result_df.empty:
        output_folder = "./pick_output" # 5년치 주봉 CSV가 저장될 폴더 이름
        
        print(f"\n{'='*60}")
        print(f"🚀 스크리닝된 {len(result_df)}개 종목에 대해 5년치 주봉 데이터 추출을 시작합니다.")
        print(f"{'='*60}\n")

        success_count = 0
        for index, row in result_df.iterrows():
            ticker = row['종목코드']
            name = row['종목명']
            
            try:
                # pick.py 의 run_pick 함수 호출
                pick.run_pick(
                    ticker=ticker, 
                    years=5, 
                    output_dir=output_folder, 
                    stock_name=name # 종목명을 바로 넘겨주어 속도 최적화
                )
                success_count += 1
            except Exception as e:
                print(f"[ERROR] {name}({ticker}) 데이터 추출 실패: {e}\n")

        print(f"\n{'='*60}")
        print(f"✅ 추출 완료: 총 {success_count}/{len(result_df)}개 종목의 주봉 데이터 저장됨")
        print(f"✅ 저장 폴더: {os.path.abspath(output_folder)}")
        print(f"{'='*60}")
