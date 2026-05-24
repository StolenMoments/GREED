# Analysis Similarity Backtest Design

> 작성일: 2026-05-24
> 상태: 설계 확정

## 1. 목적

분석 상세 화면의 분석 1건을 기준 전략으로 삼아, KOSPI200 전체 과거 주봉에서 유사한 차트 구조가 나타난 시점을 찾아 이벤트 스터디 백테스트를 실행한다.

기존 백테스트는 룰 스코어러의 매수 신호 전체를 검증한다. 이 기능은 특정 분석이 담고 있는 시장 구조와 유사한 조건이 과거 KOSPI200 종목들에서 얼마나 유효했는지 확인하는 진단 도구다.

## 2. 사용자 흐름

1. 사용자가 `/analyses/{id}` 분석 상세 화면을 연다.
2. 오른쪽 패널의 `KOSPI200 유사도 백테스트` 영역에서 유사도 임계값 `8`, `9`, `10`, `11` 중 하나를 선택한다.
3. 사용자가 실행 버튼을 누른다.
4. 서버는 백그라운드 job을 생성하고 즉시 `pending` 상태를 반환한다.
5. 프론트엔드는 job 상태를 polling한다.
6. job이 완료되면 생성된 `backtest_run_id`를 표시하고 `/backtest` 결과 화면으로 이동할 수 있게 한다.

## 3. 범위

### 포함

- 분석 1건에서 기준 피처 프로필 생성.
- KOSPI200 전체 종목의 과거 주봉에서 유사도 임계값 이상인 시점 탐색.
- 4, 8, 12, 26주 forward 수익률 계산.
- 기존 `backtest_runs`, `backtest_signals`, `backtest_stats` 결과 테이블에 저장.
- 백그라운드 job API 및 분석 상세 화면 실행 UI.

### 제외

- 사용자가 가중치를 직접 편집하는 기능.
- KOSPI200 외 universe 선택.
- 실행 중 취소.
- 백테스트 결과를 분석 markdown에 자동 반영.
- 전략 조건을 자연어로 다시 생성하는 LLM 호출.

## 4. 기준 전략 생성

서버는 대상 `Analysis`를 조회한 뒤, 해당 분석의 `ticker`와 `created_at`을 기준으로 분석 시점의 주봉 피처를 재구성한다.

재구성 방식:

- 기존 `scripts/backtest/data.py`의 주봉 OHLCV 로더를 사용한다.
- 기존 `scripts/backtest/engine.py:build_combined`로 지표와 미래 구름 행을 만든다.
- 분석 생성일 이하의 마지막 가격 주봉을 기준 index로 선택한다.
- `scripts/rule_scorer/features.py:extract_features_asof`로 피처를 만든다.
- `scripts/rule_scorer/score.py:score_features`로 룰 점수와 구조 분류를 계산한다.

기준 프로필 필드:

- `trend`
- `cloud_position`
- `ma_alignment`
- `macd_hist_direction`: `rising_positive`, `falling_negative`, `other`, `unknown`
- `rsi_bucket`: `low`, `mid`, `high`, `overheated`, `unknown`
- `volume_bucket`: `dry`, `normal`, `active`, `unknown`
- `strict_divergence`: `bullish`, `bearish`, `none`
- `future_cloud_direction`

분석 DB에 저장된 `trend`, `cloud_position`, `ma_alignment`는 화면 설명과 감사 추적용으로 보존한다. 실제 매칭 기준은 같은 코드 경로로 재계산한 룰 피처 프로필을 사용한다. 이렇게 해야 분석 markdown 파싱 품질이나 과거 분석 저장량에 의존하지 않는다.

대상 분석의 `judgment`가 매수가 아니어도 실행은 허용한다. 다만 `backtest_runs.notes`에 기준 분석의 판단과 룰 점수를 남겨 결과 해석 시 구분할 수 있게 한다.

## 5. 유사도 계산

각 후보 주봉에서 기준 프로필과 후보 프로필을 비교해 14점 만점의 유사도 점수를 계산한다.

| 항목 | 점수 |
|---|---:|
| `cloud_position` 일치 | 3 |
| `ma_alignment` 일치 | 3 |
| `trend` 일치 | 2 |
| `macd_hist_direction` 일치 | 2 |
| `rsi_bucket` 일치 | 1 |
| `volume_bucket` 일치 | 1 |
| `strict_divergence` 일치 | 1 |
| `future_cloud_direction` 일치 | 1 |

후보 시점의 유사도 점수가 사용자가 선택한 임계값 이상이면 매수 신호로 인정한다.

임계값:

- 허용값: `8`, `9`, `10`, `11`
- 기본값: `9`

`unknown` 값은 같은 `unknown`끼리도 점수를 주지 않는다. 데이터 부족끼리의 일치를 유사성으로 오해하지 않기 위해서다.

## 6. 이벤트 스터디

진입과 청산은 기존 KOSPI200 룰 백테스트와 동일하게 정의한다.

- 신호일: 유사도 조건을 만족한 주봉 index `i`
- 진입일: `i + 1` 주봉
- 진입가: `open[i + 1]`
- 4주 수익률: `close[i + 4] / open[i + 1] - 1`
- 8주 수익률: `close[i + 8] / open[i + 1] - 1`
- 12주 수익률: `close[i + 12] / open[i + 1] - 1`
- 26주 수익률: `close[i + 26] / open[i + 1] - 1`

`i + 1`이 없거나 해당 horizon의 종가가 없으면 해당 horizon은 censored로 집계한다.

warmup은 기존 백테스트와 동일하게 기본 120주를 사용한다.

## 7. 데이터 모델

### `analysis_backtest_jobs`

분석 기반 백테스트 실행 상태를 저장하는 새 테이블이다.

- `id`: PK
- `analysis_id`: FK to `analyses.id`
- `status`: `pending`, `done`, `failed`
- `similarity_threshold`: 8, 9, 10, 11
- `backtest_run_id`: nullable FK to `backtest_runs.id`
- `error_message`: nullable text
- `created_at`: 생성 시각
- `completed_at`: nullable 완료 시각

인덱스:

- `(analysis_id, created_at)`
- `(status, created_at)`

같은 `analysis_id`와 `similarity_threshold` 조합의 반복 실행은 허용한다. 주봉 캐시나 기준 분석 당시 데이터 재구성 로직이 바뀐 뒤 재실행할 수 있어야 하기 때문이다. 프론트엔드는 같은 분석의 job 중 최신 job을 기본 상태로 표시한다.

### `backtest_runs` 확장

기존 결과 조회 화면을 재사용하기 위해 분석 기반 백테스트도 `backtest_runs`에 저장한다.

추가 컬럼:

- `source_analysis_id`: nullable FK to `analyses.id`
- `strategy_kind`: nullable string. 분석 유사도 백테스트는 `analysis_similarity`
- `similarity_threshold`: nullable integer

기존 전체 룰 백테스트는 위 컬럼들이 null이어도 유효하다.

### `backtest_signals` 사용

유사도 백테스트의 신호도 기존 `backtest_signals`에 저장한다.

- `score`: 유사도 점수
- `score_bucket`: 유사도 구간으로 재해석한다.
  - `8-9`
  - `10-11`
  - `12+`
- `entry_date`, `entry_price`, `ret_4w`, `ret_8w`, `ret_12w`, `ret_26w`는 기존 의미와 같다.

### `backtest_stats` 사용

기존 집계 테이블을 그대로 사용한다.

- `score_bucket="ALL"`은 전체 유사 신호 집계다.
- bucket별 집계는 유사도 구간 기준이다.

## 8. API

### `POST /api/analyses/{analysis_id}/backtest-jobs`

분석 기반 KOSPI200 유사도 백테스트 job을 생성한다.

Request:

```json
{
  "similarity_threshold": 9
}
```

Response: `202 Accepted`

```json
{
  "id": 1,
  "analysis_id": 42,
  "status": "pending",
  "similarity_threshold": 9,
  "backtest_run_id": null,
  "error_message": null,
  "created_at": "2026-05-24T10:00:00+09:00",
  "completed_at": null
}
```

Validation:

- 분석이 없으면 `404`.
- 임계값이 `8`, `9`, `10`, `11`이 아니면 `422`.

### `GET /api/analyses/{analysis_id}/backtest-jobs`

분석에 연결된 백테스트 job 목록을 최신순으로 반환한다.

### `GET /api/analysis-backtest-jobs/{job_id}`

job 단건 상태를 반환한다. pending job은 조회 시점에 상태를 갱신할 수 있다.

## 9. 백그라운드 실행

FastAPI `BackgroundTasks`로 job을 시작한다.

실행 함수는 다음 단계를 수행한다.

1. job과 analysis를 다시 조회한다.
2. 기준 분석 프로필을 생성한다.
3. `scripts/backtest/kospi200.csv` universe를 로드한다.
4. 각 종목의 주봉 OHLCV를 로드한다.
5. `build_combined`로 피처 프레임을 만든다.
6. warmup 이후 각 주봉에서 후보 프로필을 생성한다.
7. 유사도 점수가 임계값 이상이면 `SignalRecord`를 만든다.
8. 기존 `aggregate`와 동일한 통계 집계를 수행한다.
9. `persist_run` 계열 저장 로직으로 결과를 저장한다.
10. job을 `done`으로 바꾸고 `backtest_run_id`를 연결한다.

실패 시 job은 `failed`가 되고 `error_message`에 원인을 저장한다.

## 10. 프론트엔드

분석 상세 오른쪽 컬럼에 새 패널을 추가한다.

패널 구성:

- 제목: `KOSPI200 유사도 백테스트`
- 임계값 segmented control: `8`, `9`, `10`, `11`
- 실행 버튼
- 최근 job 상태 표시
- 실패 메시지 표시
- 완료 시 `Backtest Run #id` 링크

polling:

- job 상태가 `pending`이면 2초 간격으로 조회한다.
- `done`이 되면 분석 백테스트 job 목록과 백테스트 run detail query를 invalidate한다.
- 같은 분석에 여러 job이 있으면 최신 job을 기본으로 표시하고, 완료된 과거 job은 링크 목록으로 접근할 수 있게 한다.

기존 `/backtest` 페이지는 특정 run을 바로 선택할 수 있도록 `?runId=123` query parameter를 지원한다. 분석 상세의 완료 링크는 `/backtest?runId={backtest_run_id}`로 이동한다.

## 11. 테스트 전략

### 백엔드 단위 테스트

- 기준 프로필 생성:
  - 분석 생성일 이전 마지막 주봉을 선택하는지 검증.
  - 데이터 부족 시 명확한 예외를 내는지 검증.
- 유사도 계산:
  - 완전 일치 14점.
  - `unknown`끼리는 점수를 주지 않음.
  - 임계값 필터링 검증.
- 엔진:
  - 작은 universe와 합성 주봉 데이터로 신호 생성, 수익률, censored 집계 검증.

### 백엔드 API 테스트

- `POST /api/analyses/{id}/backtest-jobs`가 job을 생성하고 background task를 등록.
- 없는 분석은 404.
- 잘못된 임계값은 422.
- `GET /api/analyses/{id}/backtest-jobs` 최신순 반환.
- job 완료 시 `backtest_run_id`가 포함됨.

### 프론트엔드 검증

- `npm run build`.
- 분석 상세 화면에서 패널이 렌더링됨.
- 실행 후 pending 상태와 완료 링크가 표시됨.
- `/backtest?runId=...` 진입 시 해당 run이 선택됨.

## 12. 리스크와 완화

1. 샘플 수가 너무 많거나 적을 수 있다.
   - 임계값을 8-11에서 선택 가능하게 해 사용자가 민감도를 조정한다.

2. 분석 저장 필드와 재계산 피처가 다를 수 있다.
   - 실제 매칭은 재계산 피처를 기준으로 하며, notes에 저장 필드와 재계산 결과를 함께 남긴다.

3. 실행 시간이 길 수 있다.
   - 백그라운드 job으로 처리하고 polling UX를 사용한다.

4. 기존 `backtest_signals.score_bucket` 의미가 룰 점수에서 유사도 구간으로 바뀐다.
   - `backtest_runs.strategy_kind`로 해석 기준을 구분한다.

## 13. 성공 기준

- 분석 상세에서 임계값을 선택해 KOSPI200 유사도 백테스트를 시작할 수 있다.
- 완료된 job은 기존 백테스트 결과 화면에서 조회할 수 있다.
- 결과 run에는 어떤 분석과 임계값에서 파생됐는지 저장된다.
- 기존 전체 룰 백테스트 CLI와 조회 화면은 깨지지 않는다.
