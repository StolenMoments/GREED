# GREED — 신규 Jira 티켓 초안

> 목적: `/runs`와 `/analyses`가 각각 실제 목록 페이지를 렌더링하도록 누락된 백엔드/프론트엔드 작업을 분리한다.  
> 실제 Jira 등록 시 `GREED-TBD-*`는 발급된 이슈 키로 교체한다.

---

## GREED-TBD-1 · [BE] 전체 분석 목록 API 추가

**Title:** `[Feat_GREED-TBD-1] Add global analyses list API`

**Overview:**  
`/analyses` 화면에서 저장된 개별 분석을 최신순으로 조회할 수 있도록 전체 분석 목록 API를 추가한다. 기존 `/runs/{run_id}/analyses`는 특정 실행 상세용으로 유지한다.

**Key Changes:**
- `backend/crud.py`
  - 전체 분석 목록 조회 함수 추가
  - 기본 정렬: `created_at desc`, `id desc`
  - 필터: `judgment`, `run_id`
- `backend/routers/analyses.py`
  - `GET /api/analyses` 엔드포인트 추가
  - 응답 모델: `list[AnalysisSummary]`
  - 잘못된 `judgment` 값은 기존 enum 검증과 동일하게 422 처리
- `backend/tests/test_analyses_router.py`
  - 전체 분석 최신순 반환 테스트
  - `judgment` 필터 테스트
  - `run_id` 필터 테스트

**Reasoning:**  
현재 API는 특정 실행에 묶인 종목 목록만 제공한다. `/analyses`는 실행과 무관하게 최근 분석을 훑는 진입점이므로 별도 전체 목록 API가 필요하다.

**Impact:**  
기존 API 경로는 유지되므로 호환성 영향은 없다. 분석 데이터가 많아질 경우 페이지네이션이 후속 개선으로 필요할 수 있다.

**Acceptance Criteria:**
- `GET /api/analyses`가 전체 분석을 최신순으로 반환한다.
- `GET /api/analyses?judgment=매수`가 매수 분석만 반환한다.
- `GET /api/analyses?run_id=2`가 해당 실행의 분석만 반환한다.
- 관련 백엔드 테스트가 통과한다.

---

## GREED-TBD-2 · [FE] RunListPage 구현 및 /runs 연결

**Title:** `[Fix_GREED-TBD-2] Render run list at runs route`

**Overview:**  
현재 `/runs`는 placeholder로 남아 있어 실행 목록을 볼 수 없다. `RunListPage`를 구현하고 `/`와 `/runs`에서 실행 목록 흐름이 동작하도록 연결한다.

**Key Changes:**
- `frontend/src/pages/RunListPage.tsx`
  - `useRuns()`로 실행 목록 조회
  - 각 항목에 생성일, 메모, 분석 종목 수 표시
  - 항목 클릭 시 `/runs/:runId` 이동
  - 새 실행 만들기 버튼 추가
  - 로딩, 에러, 빈 상태 처리
- `frontend/src/App.tsx`
  - `/runs`를 `RunListPage`로 연결
  - `/`는 `/runs`로 리다이렉트 유지
  - Runs nav가 실제 목록 페이지를 가리키도록 유지

**Reasoning:**  
기능정의와 기존 GREED-11 티켓은 실행 목록 페이지를 요구하지만 실제 구현은 placeholder에 머물러 있다. 이 페이지가 있어야 사용자가 실행 단위 분석 결과로 진입할 수 있다.

**Impact:**  
기존 `/runs/:runId` 종목 목록 동작은 유지된다. `/runs` placeholder 문구는 사라지고 실제 데이터 기반 목록으로 대체된다.

**Acceptance Criteria:**
- `/runs` 접속 시 실행 목록이 렌더링된다.
- `/` 접속 시 `/runs`로 이동하고 실행 목록이 보인다.
- 실행 항목 클릭 시 `/runs/{id}`로 이동한다.
- 새 실행 만들기 후 목록이 갱신된다.
- `npm run build`가 통과한다.

---

## GREED-TBD-3 · [FE] AnalysisListPage 구현 및 /analyses 연결

**Title:** `[Feat_GREED-TBD-3] Add global analyses list page`

**Overview:**  
`/analyses`에서 저장된 개별 분석 목록을 최신순으로 확인할 수 있는 화면을 구현한다. 사용자는 특정 실행을 거치지 않고도 최근 분석 상세로 바로 이동할 수 있어야 한다.

**Key Changes:**
- `frontend/src/api/analyses.ts`
  - `fetchAllAnalyses(filters?)` 추가
  - 필터: `judgment`, `run_id`
- `frontend/src/hooks/useAnalyses.ts`
  - 전체 분석 목록용 query key 및 hook 추가
- `frontend/src/pages/AnalysisListPage.tsx`
  - 전체 분석 최신순 목록 표시
  - 판정 필터: 전체 / 매수 / 홀드 / 매도
  - 실행 ID 필터
  - 각 항목에 생성일, 종목 코드, 종목명, 판정, 모델, 실행 ID 표시
  - 항목 클릭 시 `/analyses/:id` 이동
  - 로딩, 에러, 빈 상태 처리
- `frontend/src/App.tsx`
  - `/analyses`를 `AnalysisListPage`로 연결
  - Analyses nav가 placeholder 대신 실제 목록 페이지를 가리키도록 변경

**Reasoning:**  
`/analyses/:id` 상세 페이지는 구현되어 있지만 `/analyses` 진입점이 placeholder라 사용자가 분석 목록을 직접 탐색할 수 없다. 전역 분석 목록은 실행 목록과 다른 탐색 축을 제공한다.

**Impact:**  
신규 API `GET /api/analyses`에 의존한다. 백엔드 티켓이 선행되어야 한다. 기존 상세 페이지와 실행별 종목 목록은 유지된다.

**Acceptance Criteria:**
- `/analyses` 접속 시 전체 분석 목록이 렌더링된다.
- 판정 필터 선택 시 URL query와 목록이 함께 갱신된다.
- 실행 ID 필터 적용 시 해당 실행의 분석만 표시된다.
- 분석 항목 클릭 시 `/analyses/{id}`로 이동한다.
- `npm run build`가 통과한다.

