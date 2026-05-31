# Candidates Scan Frontend Design

**Date:** 2026-05-31  
**Status:** Approved

## Context

백엔드에 후보 종목 스캔 기능이 구현됐다 (`POST /api/candidates/scan/{analysis_id}`, `GET /api/candidates`). 기준 분석(매수 판정)과 유사한 기술적 프로필을 가진 KOSPI200 종목을 실시간으로 탐색하는 기능이다. 이를 사용자가 활용할 수 있도록 프론트엔드 UI를 추가한다.

## Route & Entry Point

- **새 라우트:** `/candidates?analysis_id=X`
- **진입 경로:** `AnalysisDetailPage`에서 judgment=`매수`인 분석에 "후보 종목 스캔 →" 링크 버튼 추가
- **Nav 항목:** App.tsx 상단 nav에 "Scan" 추가 (`/candidates`) — `analysis_id` 없이 직접 진입 시 `/analyses`로 리다이렉트

## Architecture

### 새 파일

| 파일 | 역할 |
|------|------|
| `src/pages/CandidatesPage.tsx` | 메인 페이지 컴포넌트 |
| `src/api/candidates.ts` | API 함수 |
| `src/hooks/useCandidates.ts` | React Query 훅 |

### 수정 파일

| 파일 | 변경 내용 |
|------|-----------|
| `src/types/index.ts` | `CandidateScanJob`, `CandidateScanJobStatus`, `Candidate` 타입 추가 |
| `src/App.tsx` | `/candidates` 라우트 등록, nav에 "Scan" 추가 |
| `src/pages/AnalysisDetailPage.tsx` | 매수 분석에 후보 종목 스캔 링크 버튼 추가 |

## Data Flow

### 페이지 초기 로드

1. `analysis_id` URL 파라미터 파싱 (없거나 유효하지 않으면 `/analyses`로 리다이렉트)
2. `GET /api/analyses/{analysis_id}` → 기준 종목명/티커 헤더 표시
3. `GET /api/candidates/scan-jobs/{analysis_id}` (최신 1건) → `pending`/`running` 잡 있으면 폴링 재개; 해당 잡의 `threshold`를 선택 상태로 복원
4. `GET /api/candidates?analysis_id=X&min_score={activeThreshold}` → 기존 결과 즉시 표시 (activeThreshold 기본값 12)

### 스캔 트리거

1. 사용자가 threshold 선택(12/13/14) 후 "스캔 시작" 클릭
2. `POST /api/candidates/scan/{analysis_id}` `{ threshold }` → `CandidateScanJob` (HTTP 202)
3. `jobId` local state 저장 → `useScanJobPolling(analysisId, jobId)` 활성화
4. 2초 간격 폴링: `GET /api/candidates/scan-jobs/{analysisId}/{jobId}`
5. `done` → candidates 쿼리 무효화 → 테이블 갱신
6. `failed` → 에러 메시지 카드 표시

### 티커 클릭

1. `GET /api/analyses?q={ticker}&page_size=1` 조회
2. 결과 있음 → `navigate(/analyses/{items[0].id})`
3. 결과 없음 → 인라인 확인: "분석 기록 없음 — 분석을 시작하시겠습니까?"
   - 확인 → `GET /api/runs` → `runs[0].id`로 분석 트리거 → `/jobs`로 이동

## API 함수 (`src/api/candidates.ts`)

```typescript
triggerScan(analysisId: number, payload: { threshold: number }): Promise<CandidateScanJob>
// POST /api/candidates/scan/{analysisId}

fetchScanJob(analysisId: number, jobId: number): Promise<CandidateScanJob>
// GET /api/candidates/scan-jobs/{analysisId}/{jobId}

fetchLatestScanJob(analysisId: number): Promise<CandidateScanJob | null>
// GET /api/candidates/scan-jobs/{analysisId} → items[0] or null

fetchCandidates(analysisId: number, minScore: number): Promise<Candidate[]>
// GET /api/candidates?analysis_id={analysisId}&min_score={minScore}
```

## 훅 (`src/hooks/useCandidates.ts`)

```typescript
useTriggerScan()
// Mutation: POST 트리거, onSuccess에서 jobId 콜백

useScanJobPolling(analysisId, jobId)
// Query: jobId 있을 때 2초 폴링, done/failed 시 candidates 캐시 무효화

useCandidates(analysisId, minScore)
// Query: GET /api/candidates

useLatestScanJob(analysisId)
// Query: 초기 로드용, 진행 중 잡 재개 여부 판단
```

## 타입 (`src/types/index.ts` 추가)

```typescript
export type CandidateScanJobStatus = 'pending' | 'running' | 'done' | 'failed';

export interface CandidateScanJob {
  id: number;
  analysis_id: number;
  threshold: number;
  status: CandidateScanJobStatus;
  candidate_count: number | null;
  scan_date: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface Candidate {
  id: number;
  analysis_id: number;
  scan_date: string;
  ticker: string;
  name: string;
  score: number;
  current_close: number;
  entry_price: number;
  target_price: number;
  stop_price: number;
  entry_gap_pct: number;
}
```

## UI 레이아웃

```
[브레드크럼]
  ← Analyses / 삼성전자 (005930) 후보 종목

[스캔 컨트롤 패널]  (border, bg-slate-950/45)
  Threshold   [12] [13] [14]   ← amber 세그먼트, default 12
  [스캔 시작]  ← amber-300 버튼, 스캔 중이면 비활성화

[진행 상태 카드]  ← pending/running일 때만 노출
  ◌ 스캔 중... · job #42 · running
  (2초 폴링, done/failed 시 자동 숨김)

[에러 카드]  ← failed일 때
  "스캔 실패: {error_message}"  rose 스타일

[후보 종목 테이블]
  헤더: 스캔 날짜: 2026-05-31 · 8개 종목
  ──────────────────────────────────────────────────────
  티커    종목명     점수  현재가   진입가   목표가  손절가  진입갭%
  005930  삼성전자    13   58,000  55,000  70,000  52,000   -5.2%
  (행 클릭 → 최신 분석 이동 or 분석 트리거 확인)

  빈 상태: "스캔 결과가 없습니다. 스캔을 시작하세요."
  로딩: 5행 스켈레톤 (기존 LoadingRows 패턴)
```

## 스타일 패턴

기존 코드베이스 패턴 일관성 유지:
- 배경: `bg-slate-950/45`, 테두리: `border-amber-100/10`
- 진행 중 배지: `bg-sky-400/10 text-sky-100` (JobsPage 동일)
- 실패 배지: `bg-rose-400/10 text-rose-100`
- 완료 배지: `bg-emerald-400/10 text-emerald-100`
- threshold 세그먼트: 선택 시 `bg-amber-300 text-slate-950`, 미선택 `text-slate-300 hover:bg-slate-800`

## 에러 처리

| 케이스 | 처리 |
|--------|------|
| `analysis_id` 없음 | `/analyses`로 리다이렉트 |
| 분석 로드 실패 | 에러 카드 + 재시도 버튼 |
| 스캔 트리거 실패 | 인라인 에러 메시지 |
| 스캔 job failed | rose 에러 카드, 재시도 가능 |
| 티커 분석 조회 실패 | 인라인 에러 |

## 검증

1. `npm run dev` 로컬 서버 실행
2. AnalysisDetailPage(매수 판정)에서 "후보 종목 스캔 →" 링크 확인
3. `/candidates?analysis_id={id}` 진입 → 기준 종목명 헤더 표시 확인
4. threshold 12 선택 후 "스캔 시작" → 진행 상태 카드 2초 폴링 확인
5. 스캔 완료 → 테이블 자동 갱신 확인
6. 티커 클릭 → 분석 있는 경우: `/analyses/{id}` 이동 확인
7. 티커 클릭 → 분석 없는 경우: 확인 다이얼로그 → `/jobs` 이동 확인
8. `analysis_id` 없이 진입 → `/analyses` 리다이렉트 확인
