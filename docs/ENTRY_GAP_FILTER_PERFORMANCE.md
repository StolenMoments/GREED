# 2% 진입 후보 필터 성능 개선안

> 목적: 전체 분석 목록의 `entry_gap_lte=2` 필터가 느려지는 원인을 정리하고, 작업을 나눠 진행할 수 있도록 개선 범위와 공수를 분리한다.

## 현재 구조

프론트엔드 전체 분석 목록은 `GET /api/analyses`를 호출한다. 2% 필터를 선택하면 요청 파라미터에 `entry_gap_lte=2`와 `entry_candidate`가 포함된다.

```text
AnalysisListPage
  -> useAllAnalyses(filters, pagination)
  -> GET /api/analyses?entry_gap_lte=2&entry_candidate=...
  -> list_analyses_endpoint()
  -> _refresh_candidate_stock_prices()
  -> get_analyses_page()
```

일반 목록 조회와 2% 필터 조회는 백엔드 처리 방식이 다르다.

| 구분 | 현재가 외부 조회 | 처리 방식 |
| --- | --- | --- |
| 일반 목록 | 없음 | 현재 페이지 분석만 조회하고, DB의 `stock_prices`를 고유 ticker 기준으로 묶어 조회 |
| 2% 필터 목록 | 있을 수 있음 | 조건에 맞는 전체 분석의 고유 ticker를 모아 stale 캐시를 순차 갱신한 뒤, 전체 분석을 Python에서 gap 계산/필터/정렬 |

중요한 점은 row당 외부 호출은 아니라는 것이다. 같은 ticker의 분석이 여러 개 있어도 한 요청 안에서는 고유 ticker당 최대 1회 현재가 조회가 실행된다. 다만 고유 ticker 수가 많고 캐시가 stale이면 요청 응답 시간이 외부 시세 API에 직접 묶인다.

## 병목 지점

### 1. 요청 응답 경로 안에서 외부 현재가 조회

`GET /api/analyses?entry_gap_lte=2`는 응답을 만들기 전에 `_refresh_candidate_stock_prices()`를 실행한다. 이 함수는 조건에 맞는 분석 전체에서 `entry_price`가 있는 고유 ticker를 수집하고, 캐시가 없거나 오래됐다고 판단되면 `fetch_latest_close(ticker)`를 호출한다.

현재 호출은 ticker별 순차 실행이다. FinanceDataReader 응답이 느리거나 일부 ticker 조회가 지연되면 목록 API 전체가 느려진다.

### 2. 캐시 freshness 기준이 `price_date >= today`

현재 캐시는 `stock_prices.price_date`가 오늘 날짜 이상일 때만 유효하다고 본다. 하지만 종가 데이터의 `price_date`는 마지막 거래일이다.

다음 상황에서는 최신 데이터가 있어도 stale로 판단될 수 있다.

- 장 시작 전
- 장중
- 주말
- 공휴일
- 장 마감 후 데이터 공급 지연

이 경우 같은 ticker를 여러 번 다시 조회하게 되어 2% 필터가 반복적으로 느려질 수 있다.

### 3. 2% 필터는 페이지네이션 전에 전체 대상 분석을 계산

`entry_gap_lte`가 있으면 DB에서 먼저 `limit/offset`을 적용하지 않는다. 전체 조건 대상 분석을 가져온 뒤, 각 분석의 entry candidate를 계산하고, 현재가 대비 gap을 구하고, threshold 필터와 정렬을 적용한 다음 페이지를 자른다.

정확한 `total`과 gap 기준 정렬을 위해 필요한 구조지만, 분석 데이터가 늘면 Python 처리량도 함께 늘어난다.

## 개선 옵션

### 옵션 A. 캐시 TTL 적용

**예상 공수:** 0.5일

`price_date >= today` 대신 `fetched_at` 기준 TTL을 적용한다.

예시 정책:

- `fetched_at`이 최근 30분 이내면 재조회하지 않는다.
- 종가 기준 서비스라면 1시간~6시간 TTL도 가능하다.
- 장 마감 이후 최신 종가 반영이 중요하면 별도 refresh 버튼이나 배치 갱신으로 보완한다.

**장점**

- 변경 범위가 작다.
- 장중/휴일 반복 재조회 문제를 빠르게 줄일 수 있다.
- 기존 API 응답 구조를 유지한다.

**단점**

- TTL 동안에는 최신 시세가 아닐 수 있다.
- 캐시가 전혀 없는 ticker가 많으면 첫 요청은 여전히 느릴 수 있다.

**수정 대상**

- `backend/routers/analyses.py`
- `backend/routers/stock.py`
- `backend/tests/test_analyses_router.py`
- 필요 시 `backend/tests/test_crud.py`

### 옵션 B. 목록 API에서 live refresh 제거

**예상 공수:** 1일

`GET /api/analyses`는 DB 캐시만 사용하게 하고, 현재가 갱신은 별도 API나 백그라운드 작업으로 분리한다.

가능한 흐름:

```text
GET /api/analyses?entry_gap_lte=2
  -> DB에 저장된 stock_prices 기준으로 즉시 계산/응답

POST /api/stock/prices/refresh
  -> stale ticker 목록을 갱신
  -> 완료 후 프론트가 analyses query invalidate/refetch
```

**장점**

- 목록 응답 시간이 외부 시세 API에 묶이지 않는다.
- 사용자 체감 속도가 안정된다.
- 실패한 ticker가 있어도 목록 조회는 계속 가능하다.

**단점**

- 캐시가 없는 ticker는 2% 필터 결과에서 누락되거나 현재가 없음으로 처리될 수 있다.
- 프론트에서 갱신 중 상태를 보여줄지 정책 결정이 필요하다.

**수정 대상**

- `backend/routers/analyses.py`
- `backend/routers/stock.py` 또는 신규 refresh 라우터
- `frontend/src/pages/AnalysisListPage.tsx`
- `frontend/src/api/stock.ts`
- `frontend/src/hooks/useStockPrice.ts` 또는 신규 hook
- 관련 테스트

### 옵션 C. 현재가 prewarm 및 백그라운드 갱신

**예상 공수:** 2~3일

현재가 갱신을 사용자 요청과 분리하고, 주요 ticker를 미리 갱신한다.

가능한 방식:

- 앱 시작 시 후보 ticker prewarm
- 수동 refresh API 제공
- 스케줄러 도입
- 최근 분석/매수 분석/entry price 보유 분석만 갱신
- 실패 ticker와 마지막 갱신 시각 저장 및 표시

**장점**

- 구조적으로 가장 안정적이다.
- 데이터가 늘어도 목록 조회는 DB 중심으로 유지된다.
- 외부 API 실패와 사용자 조회 경험을 분리할 수 있다.

**단점**

- 구현 범위가 넓다.
- 스케줄러 정책, 실패 재시도, UI 상태 등 결정할 부분이 많다.

**수정 대상**

- 현재가 서비스 계층 정리
- refresh 라우터 또는 작업 모듈
- 백그라운드 실행 방식
- 프론트 갱신 상태 UI
- 테스트 전반

### 옵션 D. 외부 조회 병렬화

**예상 공수:** 0.5~1일

현재 live refresh 구조를 유지하면서 stale ticker 조회를 제한된 동시성으로 병렬 처리한다.

**장점**

- stale ticker가 많을 때 응답 시간을 줄일 수 있다.
- 구조 변경이 옵션 B/C보다 작다.

**단점**

- 외부 API 호출이 여전히 목록 응답 경로 안에 있다.
- FinanceDataReader 호출 안정성, rate limit, 네트워크 실패에 취약하다.
- SQLite session과 병렬 작업을 섞을 때 구현 주의가 필요하다.

이 옵션은 단독 개선책보다는 임시 완화책에 가깝다.

## 추천 진행 순서

### 1차: TTL 캐시 적용

가장 먼저 `fetched_at` TTL을 적용한다. 작업이 작고, 현재 의심되는 반복 지연 원인을 직접 줄일 수 있다.

권장 정책:

- 기본 TTL: 30분 또는 1시간
- `/api/stock/{ticker}/price`와 `/api/analyses`의 캐시 판단 기준을 동일하게 맞춘다.
- 테스트에서는 stale 캐시와 fresh 캐시를 명확히 분리한다.

### 2차: 목록 API와 현재가 갱신 분리

1차 적용 후에도 2% 필터가 느리면, 목록 API에서 외부 조회를 제거한다.

권장 정책:

- `GET /api/analyses`는 DB 캐시만 사용한다.
- stale ticker refresh는 별도 endpoint 또는 background task로 분리한다.
- 프론트는 목록을 먼저 보여주고, 갱신 완료 후 refetch한다.

### 3차: prewarm/스케줄러

데이터가 계속 늘고 2% 필터를 자주 사용한다면 현재가 prewarm을 도입한다.

권장 정책:

- `entry_price`가 있는 ticker만 갱신한다.
- 최근 N일 또는 최근 N개 분석 ticker부터 우선한다.
- 실패 ticker는 다음 주기에서 재시도한다.

## 티켓 분리안

### GREED-TBD · [BE] 현재가 캐시 TTL 적용

**Overview:**  
2% 진입 후보 필터가 장중/휴일에 같은 ticker를 반복 조회하지 않도록 현재가 캐시 유효성 판단을 `fetched_at` TTL 기준으로 변경한다.

**Key Changes:**

- 현재가 캐시 fresh 판단 헬퍼 추가
- `/api/analyses`의 `_refresh_candidate_stock_prices()`에 TTL 적용
- `/api/stock/{ticker}/price`에도 동일 TTL 적용
- fresh/stale 캐시 테스트 추가

**Acceptance Criteria:**

- `fetched_at`이 TTL 이내인 가격은 `price_date`가 오늘이 아니어도 재조회하지 않는다.
- TTL이 지난 가격은 재조회 대상이 된다.
- 기존 2% 필터 결과는 유지된다.

### GREED-TBD · [BE/FE] 2% 필터 현재가 갱신 비동기화

**Overview:**  
전체 분석 목록 API가 외부 시세 API 응답을 기다리지 않도록 현재가 갱신을 별도 refresh 흐름으로 분리한다.

**Key Changes:**

- `/api/analyses`에서 live refresh 제거
- 현재가 bulk refresh endpoint 또는 background task 추가
- 프론트에서 2% 필터 진입 시 refresh trigger와 목록 refetch 처리
- 갱신 실패 시 목록 조회는 유지

**Acceptance Criteria:**

- `GET /api/analyses?entry_gap_lte=2`는 외부 시세 API를 직접 호출하지 않는다.
- stale 가격이 있어도 목록 API는 정상 응답한다.
- refresh 완료 후 목록의 현재가/gap 정보가 갱신된다.

## 결론

작업은 크게 나누는 것이 좋다. 현재 가장 유력한 지연 원인은 `price_date >= today` 기준 때문에 캐시가 반복적으로 stale 처리되는 점이다.

따라서 1차로 TTL 캐시만 적용하고, 체감 성능을 확인한 뒤에도 문제가 남으면 2차로 목록 API와 현재가 갱신을 분리하는 순서가 적절하다.
