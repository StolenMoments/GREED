# 백테스트 기능 설계

> 작성일: 2026-05-24
> 상태: 설계 확정 (구현 전)

## 1. 목적

룰 기반 주봉 스코어러(`rule_scorer`)의 **매수 신호가 실제로 예측력이 있는지**를 KOSPI200 종목의 과거 차트로 검증한다.
신호 발생 후 고정 보유기간 동안의 forward 수익률을 이벤트 스터디 방식으로 측정해, 승률과 수익률 분포로 신호 품질을 평가한다.

## 2. 요구사항 요약

| 항목 | 결정 |
|---|---|
| 신호 소스 | 룰 기반 스코어러(`scripts/rule_scorer`) 판정 == **매수** |
| 진입 방식 | **이벤트 스터디** — 매수 판정이 난 모든 주봉에서 각각 측정 |
| 청산 | **고정 보유기간** forward 수익률 (4·8·12·26주) |
| 유니버스 | **현재 KOSPI200 구성종목** 고정 (생존편향 감수) |
| 데이터 | FDR로 종목별 가용 최대 과거, 주봉 데이터 **DB 캐시 재사용** |
| 지표 | **승률 + 수익률 분포**(평균/중앙값/표준편차/p25/p75/min/max) |
| 구조 | CLI 배치 계산 → DB 저장 → 백엔드 API + 프론트 페이지 조회 (읽기 전용) |

기간은 3년 등으로 고정하지 않고 FDR에서 종목별로 받을 수 있는 최대 과거를 사용한다.

## 3. 아키텍처 & 데이터 흐름

```
[CLI 배치: scripts/backtest.py]
  KOSPI200 유니버스 해석
        │
        ▼
  종목별 일봉 수집 (FDR, 최대 과거)  ──▶  price_bars(1d) 캐시 재사용
        │
        ▼
  주봉 리샘플 + 지표 계산 (공용 모듈)  ──▶  weekly_bars 테이블 저장(재사용)
        │
        ▼
  이벤트 스터디 엔진
   (매 주봉 as-of 피처 재구성 → 스코어링 → 매수 주 forward 수익률)
        │
        ▼
  결과 영속화: backtest_runs / backtest_signals / backtest_stats

[백엔드 FastAPI]  결과 테이블만 읽어 API 제공 (무거운 연산 없음)
        │
        ▼
[프론트 /backtest 페이지]  승률 · 수익률 분포 · 점수구간 비교 시각화
```

핵심 원칙: **무거운 연산은 전부 CLI에**, 웹은 저장된 결과만 읽는다.

### 3-1. 공용 지표 모듈 추출 (타깃 리팩터)

`scripts/pick.py`에 있는 주봉 리샘플 + 지표 계산 파이프라인을 공용 모듈 `scripts/weekly_indicators.py`로 추출한다.
- 이동: `add_moving_averages`, `add_liquidity_indicators`, `add_volatility_indicators`, `add_momentum_indicators`, `add_signal_indicators`, 다이버전스 계산, `add_ichimoku`, `add_ichimoku_derived_indicators`, 주봉 리샘플(`W-MON`), `append_future_cloud`.
- `pick.py`는 이 모듈을 import 하도록 변경(동작 보존 리팩터).
- 백테스트 엔진도 동일 모듈을 사용 → 중복 제거 + 주봉 정렬/지표 정의 일치 보장.

## 4. DB 스키마 (신규 테이블 4개)

SQLAlchemy 모델은 `backend/models.py`에 추가한다.

### 4-1. `weekly_bars` — 주봉 지표 시리즈 캐시
- PK: `(ticker, bar_date)`
- 컬럼: `open, high, low, close, volume, trading_value, volume_ma20, volume_ratio_20, ma20, ma60, ma120, atr14, atr14_pct, rsi14, macd, macd_signal, macd_hist, ma20_60_cross, ma60_120_cross, macd_signal_cross, strict_divergence, ichi_conv, ichi_base, ichi_lead1, ichi_lead2, ichi_lag, cloud_top, cloud_bottom, cloud_thickness, cloud_thickness_pct` (= 주봉 CSV 컬럼과 동일), `fetched_at`
- 미래 구름 행(close=NaN)은 **저장하지 않는다.** `ichi_lead1/lead2`가 이미 `shift(26)`된 값이라 as-of 시점의 미래 구름은 인접 행에서 재구성 가능하다.
- 인덱스: `(ticker, bar_date)` 조회용.

### 4-2. `backtest_runs` — 실행 단위
- `id (PK), created_at, universe(="KOSPI200"), buy_threshold, horizons(="4,8,12,26"), warmup_weeks, data_start, data_end, ticker_count, signal_count, notes`
- 실행 시점의 파라미터 스냅샷.

### 4-3. `backtest_signals` — 신호별 레코드 (드릴다운/히스토그램용)
- `id (PK), run_id (FK), ticker, name, signal_date, score, score_bucket, entry_date, entry_price, ret_4w, ret_8w, ret_12w, ret_26w`
- `ret_*`는 nullable (우측 절단 시 NULL).
- 인덱스: `(run_id, ticker)`, `(run_id, score_bucket)`.

### 4-4. `backtest_stats` — 집계 헤드라인 (웹 고속 조회용)
- PK: `(run_id, horizon, score_bucket)`
- 컬럼: `count, censored_count, win_rate, mean, median, std, p25, p75, min, max`
- `score_bucket`에는 전체 합산용 특수값 `"ALL"`도 포함.
- CLI가 미리 계산해 저장하므로 API는 단순 조회만 수행.

## 5. 이벤트 스터디 엔진 (정확성 핵심)

### 5-1. as-of 피처 재구성 (룩어헤드 차단)
- 종목당 지표 시리즈를 **한 번만** 계산한다.
- 각 신호 후보 주 인덱스 `i`에 대해:
  - `price_window = df[:i+1]` — i주까지의 데이터만 사용.
  - 미래 구름 = `df[i+1 : i+27]`의 `ichi_lead1/lead2`. 이 값은 `shift(26)`으로 산출되어 `i` 시점 이하 데이터에만 의존 → **룩어헤드 없음**.
  - `features.py`에 인덱스 기반 `extract_features_asof(df, i)`를 추가한다. 기존 `extract_features` 로직을 재사용하되 CSV 슬라이싱 대신 인덱스로 동작한다.
- **워밍업**: MA120 등 최장 롤링 윈도가 유효해지는 **120주** 이후부터 스코어링한다(설정값 `warmup_weeks`).

### 5-2. 진입 / 청산 / 수익률 (누수 없는 정의)
- 신호 주 인덱스 `i`에서 룰 판정 == 매수 →
  - **진입가 = `open[i+1]`** (신호 주 마감 후 첫 거래 가능 시점, 현실적이며 누수 없음).
  - horizon `N`별 **청산가 = `close[i+N]`**.
  - `forward_return_N = close[i+N] / open[i+1] − 1`.
- `i+1` 또는 `i+N`이 시리즈 끝을 넘으면 해당 (신호, horizon)은 **우측 절단**으로 분리 집계하고 승률 분모에서 제외한다(`censored_count`).

### 5-3. 점수 구간 (score_bucket)
- 매수 신호를 점수로 구간화: `[4–5]`, `[6–7]`, `[8+]`.
- 목적: "확신도↑ → 승률↑" 단조성 검증.

### 5-4. 집계 (CLI에서 계산)
- `(horizon, score_bucket)`별 및 `(horizon, "ALL")`별로:
  - `win_rate` = (ret > 0 인 신호 수) / (절단 제외 신호 수)
  - `mean, median, std, p25, p75, min, max` (numpy/pandas)
  - `count, censored_count`
- 결과를 `backtest_stats`에 저장.

## 6. 백엔드 API (읽기 전용)

`backend/routers/stats.py` 패턴을 따라 `backend/routers/backtest.py`를 추가하고 `backend/main.py`에 라우터 등록.

- `GET /backtest/runs` — 실행 목록(파라미터, signal_count, created_at).
- `GET /backtest/runs/{id}` — 실행 상세 + `backtest_stats` (horizon × score_bucket 집계).
- `GET /backtest/runs/{id}/signals` — 신호 목록(ticker / horizon / score_bucket 필터, 페이지네이션) + horizon별 수익률 히스토그램 버킷 데이터.

스키마는 `backend/schemas.py`에 Pydantic 모델로 정의.

`POST /backtest/runs`(웹 트리거 실행)는 v1 범위 밖이며, 추후 파라미터화 확장 지점으로 남긴다.

## 7. 프론트엔드 `/backtest` 페이지

기존 stats 페이지의 스타일/컴포넌트를 재사용한다.
- 실행 선택기(기본=최신 실행) + 파라미터 표시.
- **헤드라인 표**: horizon(4/8/12/26주) × `신호 수 · 승률 · 평균 · 중앙값`.
- **수익률 분포**: horizon별 히스토그램 + 박스 통계(p25/p50/p75, min/max, std).
- **점수 구간 비교**: 버킷별 승률·평균수익률 막대(단조성 확인).
- (선택) 종목별 평균수익률 상·하위 드릴다운 표.

## 8. CLI (`scripts/backtest.py`)

실행 단계:
1. KOSPI200 유니버스 해석 (10절 리스크 1 참고).
2. 종목별: 일봉 로드/갱신(`price_bars` 1d 캐시, 최대 과거) → 주봉 리샘플 + 지표 계산(공용 모듈) → `weekly_bars` upsert.
3. 이벤트 스터디: 워밍업 이후 매 주봉 as-of 피처 재구성 → 스코어링 → 매수 신호의 horizon별 forward 수익률 수집.
4. 영속화: `backtest_runs`, `backtest_signals`, `backtest_stats`.
5. (선택) `rule_score.py`처럼 마크다운/CSV 요약 출력.

`weekly_bars` 캐시 덕분에 재실행은 빨라진다(레주메는 v1 범위 밖).

## 9. 테스트 전략

- **골든 테스트**: `extract_features_asof(df, last_index)` == 기존 CSV 기반 `extract_features(load_csv(...))` 결과 (`pick_output` 실제 CSV로 검증).
- **누수 테스트**: 시리즈를 `i`에서 잘라도 `i` 시점 피처가 동일함을 확인.
- **수익률/절단 단위 테스트**: 합성 시리즈로 forward 수익률·우측 절단 검증.
- **엔진 테스트**: 알려진 신호/수익을 가진 작은 시리즈로 end-to-end.
- **집계 테스트**: 승률·분위수 계산 정확성.
- **백엔드 라우터 테스트**: 시드 DB로 list/detail/signals (기존 `backend/tests` 패턴).

## 10. 리스크 / 확인 사항

1. **FDR KOSPI200 리스트 제공 여부** — 구현 계획 단계에서 `fdr.StockListing('KOSPI200')` 검증. 안 되면 정적 리스트(CSV/JSON) 폴백.
2. **생존편향** — 현재 구성종목 고정이라 과거 편입/편출 미반영(합의됨).
3. **첫 실행 속도** — KOSPI200 전체 FDR 수집은 느림, 캐시 후 빨라짐(배치라 허용).
4. **누수 차단 정확성** — as-of 재구성이 최고 위험 영역 → 골든 테스트 + 누수 테스트로 완화.

## 11. v1 범위 밖 (추후 확장)

- 웹에서 파라미터(임계값/기간/horizon) 입력 후 비동기 실행(`POST /backtest/runs`).
- 벤치마크(KOSPI200 지수 보유) 대비 초과수익 비교.
- 목표가/손절가(ATR 기반) 청산 방식.
- 과거 시점 KOSPI200 멤버십 반영(생존편향 제거).
- 백테스트 레주메/중간 진행 상태 저장.
