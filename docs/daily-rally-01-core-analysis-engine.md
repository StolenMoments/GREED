# Daily 20d +40% Rally Core Analysis Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 일봉 기준 `D+20` 거래일 수익률이 `+40%` 이상인 급등 이벤트를 라벨링하고, `D`까지의 데이터만으로 설명 규칙을 mining하는 분석 엔진을 만든다.

**Architecture:** 신규 엔진은 `scripts/backtest/daily_rally.py`에 둔다. 데이터 로딩은 기존 `scripts/backtest/data.py`의 일봉 캐시(`price_bars`, interval `1d`)를 사용하고, 주봉 파생 피처가 필요할 때만 같은 모듈의 주봉 로더와 `weekly_indicators`를 재사용한다. 엔진 출력은 문서 2의 저장 계층이 그대로 사용할 수 있는 dataclass 리스트로 반환한다.

**Tech Stack:** Python 3.13, pandas, numpy, SQLAlchemy Session, pytest.

---

## 목표

- 전략 키는 `daily_20d_40pct_rally`로 고정한다.
- 각 종목의 각 거래일 `D`에 대해 `D+20` 거래일 종가 기준 forward return을 계산한다.
- positive label은 `close[D+20] / close[D] - 1 >= 0.40`이다.
- 피처 생성은 반드시 `D`까지 확정된 일봉/주봉 데이터만 사용한다.
- 같은 종목에서 positive가 연속 발생하면 첫 이벤트만 남기고 이후 20거래일 안의 positive는 제거한다.
- positive 샘플과 control 샘플을 비교해 규칙별 `support`, `precision`, `base_rate`, `lift`, `score`를 산출한다.

## 변경 파일

- Create: `scripts/backtest/daily_rally.py`
- Modify: `scripts/backtest/__init__.py`
- Test: `backend/tests/test_daily_rally_engine.py`

## 데이터 계약

`scripts/backtest/daily_rally.py`에 아래 dataclass를 둔다.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


DAILY_RALLY_STRATEGY_KIND = "daily_20d_40pct_rally"
RALLY_HORIZON_DAYS = 20
RALLY_THRESHOLD = 0.40
FORWARD_RETURN_DAYS = (20, 40, 60, 120)


@dataclass(slots=True)
class DailyRallySample:
    ticker: str
    name: str
    signal_date: date
    close_price: float
    label: int
    forward_returns: dict[int, float | None] = field(default_factory=dict)
    features: dict[str, bool | int | float | str | None] = field(default_factory=dict)


@dataclass(slots=True)
class DailyRallyRule:
    rule_key: str
    rule_label: str
    support: int
    positives: int
    total_matches: int
    precision: float
    base_rate: float
    lift: float
    score: float


@dataclass(slots=True)
class DailyRallyCandidate:
    ticker: str
    name: str
    signal_date: date
    close_price: float
    matched_rules: list[str] = field(default_factory=list)
    matched_rule_count: int = 0
    max_rule_score: float | None = None
    mean_rule_score: float | None = None
    features: dict[str, bool | int | float | str | None] = field(default_factory=dict)


@dataclass(slots=True)
class DailyRallyBacktestResult:
    samples: list[DailyRallySample]
    rules: list[DailyRallyRule]
    current_candidates: list[DailyRallyCandidate]
    ticker_count: int
    data_start: date | None
    data_end: date | None
```

## 피처 목록

일봉 피처는 `D` 행까지 rolling/ewm으로 계산한다.

- `ret_1d`, `ret_5d`, `ret_20d`, `ret_60d`: 종가 수익률.
- `volume_ratio_20d`: 당일 거래량 / 20일 평균 거래량.
- `trading_value_ratio_20d`: 당일 거래대금 / 20일 평균 거래대금.
- `range_pct`: `(high - low) / close`.
- `close_to_20d_high`: `close / rolling_high_20d - 1`.
- `close_to_60d_high`: `close / rolling_high_60d - 1`.
- `close_to_20d_low`: `close / rolling_low_20d - 1`.
- `ma5_gt_ma20`, `ma20_gt_ma60`, `ma60_up`: 이동평균 정렬과 기울기.
- `rsi14`: 14일 RSI.
- `atr_pct_14`: 14일 ATR / 종가.

주봉 피처는 `D`가 속한 주의 미완성 주봉을 사용하지 않는다. `D` 이전에 종료된 마지막 주봉만 as-of로 join한다.

- `weekly_close_gt_ma20`
- `weekly_ma5_gt_ma20`
- `weekly_volume_ratio_20w`
- `weekly_cloud_position`: `above_cloud`, `inside_cloud`, `below_cloud`
- `weekly_span2_breakout_recent_4w`: 최근 4개 완료 주봉 중 span2 상향 돌파 여부.

## 규칙 후보

연속형 피처는 threshold predicate로 변환한다.

- `ret_20d >= 0.10`, `ret_20d >= 0.20`, `ret_60d >= 0.30`
- `volume_ratio_20d >= 2`, `volume_ratio_20d >= 3`
- `trading_value_ratio_20d >= 2`, `trading_value_ratio_20d >= 3`
- `close_to_20d_high >= -0.03`, `close_to_60d_high >= -0.05`
- `close_to_20d_low >= 0.20`
- `range_pct >= 0.08`
- `rsi14 >= 60`, `rsi14 >= 70`
- `atr_pct_14 >= 0.04`

불리언/범주형 피처는 동등 조건으로 변환한다.

- `ma5_gt_ma20 == True`
- `ma20_gt_ma60 == True`
- `ma60_up == True`
- `weekly_close_gt_ma20 == True`
- `weekly_ma5_gt_ma20 == True`
- `weekly_cloud_position == above_cloud`
- `weekly_span2_breakout_recent_4w == True`

2개 조합 규칙은 단일 규칙 상위 30개에서만 생성한다. 조합 수 폭증을 막기 위해 3개 이상 조합은 만들지 않는다.

## 구현 단계

### Task 1: 라벨링과 forward return

- [ ] `scripts/backtest/daily_rally.py`에 상수와 dataclass를 추가한다.
- [ ] `_forward_return(df, i, horizon)`를 추가한다. `i + horizon >= len(df)`이면 `None`을 반환하고, 기준 종가가 0 이하이면 `None`을 반환한다.
- [ ] `label_daily_rallies(df)`를 추가한다. `valid_daily_ohlcv`를 통과한 일봉을 날짜 오름차순으로 사용하고, `D+20`이 있는 행만 `DailyRallySample` 후보로 만든다.
- [ ] 종목별 중복 제거를 구현한다. positive가 발생한 index를 `last_positive_i`로 기억하고 `i - last_positive_i <= 20`이면 해당 positive는 label `0`으로 낮추는 것이 아니라 샘플에서 제외한다.
- [ ] `backend/tests/test_daily_rally_engine.py`에 `test_label_daily_rallies_uses_d_plus_20_close`를 추가한다. 21번째 이후 종가만 급등하게 만든 synthetic frame으로 label 1을 검증한다.
- [ ] `test_label_daily_rallies_deduplicates_positive_events_within_20_sessions`를 추가한다. index 10과 15가 모두 +40% 조건을 만족해도 index 10만 남는지 검증한다.
- [ ] 실행: `.venv/Scripts/python.exe -m pytest backend/tests/test_daily_rally_engine.py -v`

### Task 2: 일봉 피처 생성

- [ ] `build_daily_features(df)`를 추가한다. 결과 index는 입력 일봉 index와 같게 유지한다.
- [ ] rolling window는 `min_periods`를 window와 동일하게 둔다. 충분한 과거 데이터가 없으면 feature 값은 `NaN`이며 샘플 생성에서 제외한다.
- [ ] RSI와 ATR 계산을 엔진 내부 helper로 구현한다. 새 외부 의존성은 추가하지 않는다.
- [ ] `attach_daily_features(samples, feature_df)`를 추가한다. 샘플 날짜에 해당하는 feature row를 dict로 넣고, 필수 피처 중 `NaN`이 있으면 샘플을 제외한다.
- [ ] 테스트 `test_daily_features_do_not_use_future_rows`를 추가한다. `D+1` 이후 가격을 크게 바꿔도 `D`의 `ret_20d`, `volume_ratio_20d`, `ma5_gt_ma20` 값이 바뀌지 않는지 검증한다.
- [ ] 실행: `.venv/Scripts/python.exe -m pytest backend/tests/test_daily_rally_engine.py -v`

### Task 3: 완료 주봉 as-of 피처

- [ ] `build_weekly_asof_features(daily_df, weekly_df)`를 추가한다.
- [ ] `weekly_df`는 이미 완료된 주봉만 포함한다고 가정하지 않는다. 각 일봉 날짜 `D`에 대해 `weekly.index < D`인 마지막 주봉 행만 사용한다.
- [ ] `weekly_indicators.add_all_indicators`와 `append_future_cloud`를 재사용해 cloud 관련 피처를 만든다.
- [ ] `attach_weekly_features(samples, weekly_feature_df)`를 추가한다.
- [ ] 테스트 `test_weekly_features_use_last_completed_week_only`를 추가한다. 금요일 전 일봉에 같은 주 주봉 값이 붙지 않는지 검증한다.
- [ ] 실행: `.venv/Scripts/python.exe -m pytest backend/tests/test_daily_rally_engine.py -v`

### Task 4: positive/control 샘플 생성

- [ ] `build_samples_for_ticker(ticker, name, daily_df, weekly_df=None)`를 추가한다.
- [ ] control은 positive가 아닌 모든 유효 샘플을 사용하되, positive index의 ±20거래일 범위는 제외한다. 급등 직전/직후의 유사 이벤트가 control을 오염시키지 않게 하기 위함이다.
- [ ] `build_daily_rally_samples(db, universe=None)`를 추가한다. 기본 universe는 `load_active_universe(db)`이고 일봉은 `load_daily_ohlcv(db, ticker, fetch_missing=False)`로 읽는다.
- [ ] 데이터가 부족한 종목은 건너뛴다. 최소 길이는 `180 + 120` 거래일로 둔다.
- [ ] 테스트 `test_control_samples_exclude_positive_neighborhood`를 추가한다.
- [ ] 실행: `.venv/Scripts/python.exe -m pytest backend/tests/test_daily_rally_engine.py -v`

### Task 5: 규칙 mining과 ranking

- [ ] `predicate_matches(sample, predicate)`와 `build_rule_candidates(samples)`를 추가한다.
- [ ] `rank_rules(samples, min_support=5, min_precision=0.15)`를 추가한다.
- [ ] `base_rate = positive_count / total_sample_count`.
- [ ] `support = positives matched by rule`.
- [ ] `total_matches = all samples matched by rule`.
- [ ] `precision = support / total_matches`.
- [ ] `lift = precision / base_rate`이고 `base_rate == 0`이면 `lift = 0`.
- [ ] `score = support * max(lift - 1, 0) * precision`.
- [ ] `score` 내림차순, `precision` 내림차순, `support` 내림차순으로 정렬한다.
- [ ] 테스트 `test_rank_rules_computes_support_precision_lift_and_score`를 추가한다. 작은 샘플 6개로 정확한 수치를 검증한다.
- [ ] 실행: `.venv/Scripts/python.exe -m pytest backend/tests/test_daily_rally_engine.py -v`

### Task 6: 현재 후보 생성

- [ ] `find_current_candidates(samples, rules, as_of=None)`를 추가한다.
- [ ] 각 종목의 마지막 유효 샘플만 후보 평가 대상으로 삼는다.
- [ ] 상위 규칙 중 하나 이상 match하면 `DailyRallyCandidate`로 반환한다.
- [ ] 후보의 `matched_rule_count`, `max_rule_score`, `mean_rule_score`를 계산한다.
- [ ] 정렬은 `max_rule_score` 내림차순, `matched_rule_count` 내림차순, `ticker` 오름차순이다.
- [ ] 테스트 `test_find_current_candidates_uses_latest_sample_per_ticker`를 추가한다.
- [ ] 실행: `.venv/Scripts/python.exe -m pytest backend/tests/test_daily_rally_engine.py -v`

### Task 7: 엔진 엔트리포인트

- [ ] `run_daily_rally_backtest(db, universe=None)`를 추가한다.
- [ ] 반환값은 `DailyRallyBacktestResult`이며 `samples`, `rules`, `current_candidates`, `ticker_count`, `data_start`, `data_end`를 채운다.
- [ ] `scripts/backtest/__init__.py`에서 `DAILY_RALLY_STRATEGY_KIND`, `run_daily_rally_backtest`를 export한다.
- [ ] 테스트 `test_run_daily_rally_backtest_returns_result_shape`를 추가한다. `monkeypatch`로 universe와 loader를 synthetic data에 연결해 외부 네트워크 없이 검증한다.
- [ ] 실행: `.venv/Scripts/python.exe -m pytest backend/tests/test_daily_rally_engine.py -v`

## 테스트

필수 실행:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_daily_rally_engine.py -v
```

회귀 확인:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_backtest_engine.py backend/tests/test_preload_daily.py -v
```

완료 기준:

- `D+20` 라벨이 정확히 계산된다.
- 같은 종목의 20거래일 중복 positive가 제거된다.
- 모든 피처가 `D` 이후 값을 사용하지 않는다는 테스트가 있다.
- 규칙 ranking 지표가 정의대로 계산된다.
- 엔진이 DB Session과 universe 입력을 받아 네트워크 없이 테스트 가능하다.
