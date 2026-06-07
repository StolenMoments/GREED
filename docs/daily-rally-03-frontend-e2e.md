# Daily 20d +40% Rally Frontend And End-To-End UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 백테스트 화면에서 `daily_20d_40pct_rally` 전략 실행, 완료 run 자동 선택, rule insight, 현재 후보, 20d/40d/60d/120d forward return 통계를 확인할 수 있게 한다.

**Architecture:** 기존 `BacktestPage.tsx`의 strategy job polling과 run selector를 재사용한다. API 타입과 fetcher는 `frontend/src/api/backtest.ts`에 추가하고, daily rally 전용 패널은 `BacktestPage.tsx` 안에서 작게 시작한다. 로직이 커지면 같은 PR 안에서 `frontend/src/pages/DailyRallyPanels.tsx`로 분리한다.

**Tech Stack:** React 19, TypeScript, Vite, TanStack Query, Tailwind, Vitest.

---

## 목표

- `BacktestStrategyKind`에 `daily_20d_40pct_rally`를 추가한다.
- 전략 실행 패널에 `Run Daily 20d +40% Rally` 버튼을 추가한다.
- daily rally run 상세에서 아래를 보여준다.
  - 이벤트 요약
  - 상위 규칙 table
  - 현재 후보 table
  - 20d/40d/60d/120d forward return 통계
- 기존 polling과 완료 run 자동 선택 흐름을 유지한다.
- 프론트 빌드와 렌더링 테스트를 통과한다.

## 변경 파일

- Modify: `frontend/src/api/backtest.ts`
- Modify: `frontend/src/pages/backtestStrategySelection.ts`
- Modify: `frontend/src/pages/backtestStrategySelection.test.ts`
- Modify: `frontend/src/pages/BacktestPage.tsx`
- Modify: `frontend/src/pages/backtestHighlights.ts`
- Modify: `frontend/src/pages/backtestHighlights.test.ts`
- Test: existing Vitest suite

## API 타입

`frontend/src/api/backtest.ts`에 추가한다.

```ts
export type BacktestStrategyKind =
  | 'ichimoku_span2_breakout'
  | 'daily_20d_40pct_rally';

export interface DailyRallyRuleStat {
  id: number;
  run_id: number;
  rule_key: string;
  rule_label: string;
  support: number;
  positives: number;
  total_matches: number;
  precision: number;
  base_rate: number;
  lift: number;
  score: number;
}

export interface DailyRallyInsights {
  run_id: number;
  rule_count: number;
  rules: DailyRallyRuleStat[];
}

export interface DailyRallyCandidate {
  id: number;
  run_id: number;
  ticker: string;
  name: string;
  signal_date: string;
  close_price: number;
  matched_rules: string[];
  matched_rule_count: number;
  max_rule_score: number | null;
  mean_rule_score: number | null;
  features: Record<string, boolean | number | string | null>;
}

export interface DailyRallyCandidates {
  run_id: number;
  candidate_count: number;
  candidates: DailyRallyCandidate[];
}
```

Fetcher:

```ts
export async function fetchDailyRallyInsights(runId: number): Promise<DailyRallyInsights> {
  const response = await apiClient.get<DailyRallyInsights>(
    `/backtest/runs/${runId}/daily-rally-insights`,
  );
  return response.data;
}

export async function fetchDailyRallyCandidates(runId: number): Promise<DailyRallyCandidates> {
  const response = await apiClient.get<DailyRallyCandidates>(
    `/backtest/runs/${runId}/daily-rally-candidates`,
  );
  return response.data;
}
```

## 구현 단계

### Task 1: strategy kind와 실행 버튼

- [ ] `frontend/src/api/backtest.ts`의 `BacktestStrategyKind` union에 `daily_20d_40pct_rally`를 추가한다.
- [ ] `frontend/src/pages/backtestStrategySelection.ts`가 latest job의 strategy kind를 고려하도록 확장한다. 완료된 job이 daily rally든 span2든 `backtest_run_id`가 있으면 선택 대상으로 인정한다.
- [ ] `BacktestPage.tsx`에서 mutation을 두 개로 분리한다.
  - `runSpan2Mutation`: `createBacktestStrategyJob('ichimoku_span2_breakout')`
  - `runDailyRallyMutation`: `createBacktestStrategyJob('daily_20d_40pct_rally')`
- [ ] `StrategyJobPanel` props를 확장한다.
  - `onRunSpan2`
  - `onRunDailyRally`
  - `isStartingSpan2`
  - `isStartingDailyRally`
- [ ] 패널에 버튼 두 개를 배치한다.
  - `Run Ichimoku Span2 Breakout`
  - `Run Daily 20d +40% Rally`
- [ ] 둘 중 하나라도 active job이 있으면 두 버튼 모두 disabled 처리한다. 백엔드는 active strategy job을 하나만 허용한다.
- [ ] `frontend/src/pages/backtestStrategySelection.test.ts`에 daily rally 완료 job도 run 선택으로 반영되는 테스트를 추가한다.
- [ ] 실행: `cd frontend; npm test -- backtestStrategySelection`

### Task 2: daily rally API fetcher와 query

- [ ] `frontend/src/api/backtest.ts`에 `DailyRallyRuleStat`, `DailyRallyInsights`, `DailyRallyCandidate`, `DailyRallyCandidates` 타입을 추가한다.
- [ ] 같은 파일에 `fetchDailyRallyInsights`, `fetchDailyRallyCandidates`를 추가한다.
- [ ] `BacktestPage.tsx`에서 `const isDailyRally = detail?.strategy_kind === 'daily_20d_40pct_rally';`를 추가한다.
- [ ] daily rally query를 추가한다.

```ts
const dailyRallyInsightsQuery = useQuery({
  queryKey: ['backtest', 'run', runId, 'daily-rally-insights'],
  queryFn: () => fetchDailyRallyInsights(runId as number),
  enabled: runId !== null && isDailyRally,
});

const dailyRallyCandidatesQuery = useQuery({
  queryKey: ['backtest', 'run', runId, 'daily-rally-candidates'],
  queryFn: () => fetchDailyRallyCandidates(runId as number),
  enabled: runId !== null && isDailyRally,
});
```

- [ ] run이 바뀌면 query key가 바뀌므로 별도 reset state는 만들지 않는다.
- [ ] 실행: `cd frontend; npm test -- backtestHighlights`

### Task 3: forward return 통계 표시

- [ ] 기존 `HorizonTable`이 horizon 숫자만 표시한다면 daily rally일 때 `20d`, `40d`, `60d`, `120d`로 label을 바꾼다.
- [ ] helper `formatHorizonLabel(detail, horizon)`를 추가한다.

```ts
function formatHorizonLabel(detail: BacktestRunDetail, horizon: number): string {
  if (detail.strategy_kind === 'daily_20d_40pct_rally') {
    return `${horizon}d`;
  }
  return `${horizon}w`;
}
```

- [ ] `HorizonTable` props를 `detail: BacktestRunDetail`로 확장하고 내부에서 `detail.stats`를 사용한다.
- [ ] daily rally run은 `score_bucket`이 `positive`, `control`, `ALL`일 수 있으므로 bucket display helper를 추가한다.
  - `positive` -> `Positive Events`
  - `control` -> `Controls`
  - `ALL` -> `All Samples`
  - 그 외 기존 bucket은 그대로 표시
- [ ] `frontend/src/pages/backtestHighlights.test.ts`에 daily horizon label 테스트를 추가한다.
- [ ] 실행: `cd frontend; npm test -- backtestHighlights`

### Task 4: daily rally summary panel

- [ ] `BacktestPage.tsx`에 `DailyRallySummaryPanel` 컴포넌트를 추가한다.
- [ ] 표시 필드:
  - run id
  - `detail.signal_count`
  - `detail.ticker_count`
  - `detail.data_start` ~ `detail.data_end`
  - top rule count: `insights.rule_count`
  - current candidate count: `candidates.candidate_count`
- [ ] 숫자와 날짜 formatter는 기존 파일의 formatter helper를 재사용한다.
- [ ] insights/candidates query가 loading이면 panel 내부에 `LoadingBlock`을 보여준다.
- [ ] query error면 해당 영역만 짧은 error state를 보여주고 전체 run 상세는 유지한다.
- [ ] daily rally 분기에서 `SummaryStrip` 대신 `DailyRallySummaryPanel`을 먼저 렌더링한다.
- [ ] 실행: `cd frontend; npm run build`

### Task 5: 상위 규칙 table

- [ ] `DailyRallyRulesTable` 컴포넌트를 추가한다.
- [ ] columns:
  - Rule
  - Support
  - Precision
  - Base Rate
  - Lift
  - Score
- [ ] percent formatter는 `precision`, `base_rate`에 적용한다.
- [ ] `lift`, `score`는 소수점 2자리로 표시한다.
- [ ] row key는 `rule.id`를 사용한다.
- [ ] rule이 없으면 빈 상태 `No mined rules for this run.`을 보여준다.
- [ ] daily rally 분기에서 summary 다음에 렌더링한다.
- [ ] 실행: `cd frontend; npm run build`

### Task 6: 현재 후보 table

- [ ] `DailyRallyCandidatesTable` 컴포넌트를 추가한다.
- [ ] columns:
  - Ticker
  - Name
  - Signal Date
  - Close
  - Matched Rules
  - Max Score
  - Mean Score
- [ ] `matched_rules`는 최대 3개만 inline으로 표시하고, 4개 이상이면 `+N` suffix를 붙인다.
- [ ] close price는 기존 가격 formatter가 있으면 재사용하고, 없으면 `Intl.NumberFormat('ko-KR')`로 표시한다.
- [ ] 후보가 없으면 빈 상태 `No current candidates for this run.`을 보여준다.
- [ ] daily rally 분기에서 rules table 다음에 렌더링한다.
- [ ] 실행: `cd frontend; npm run build`

### Task 7: daily rally 전용 렌더링 분기

- [ ] `BacktestPage.tsx`의 run detail 렌더링 조건에 daily rally를 추가한다.

```tsx
{detail.strategy_kind === 'daily_20d_40pct_rally' ? (
  <>
    <DailyRallySummaryPanel
      candidates={dailyRallyCandidatesQuery.data}
      detail={detail}
      insights={dailyRallyInsightsQuery.data}
      isLoading={dailyRallyInsightsQuery.isLoading || dailyRallyCandidatesQuery.isLoading}
    />
    <DailyRallyRulesTable insights={dailyRallyInsightsQuery.data} />
    <DailyRallyCandidatesTable candidates={dailyRallyCandidatesQuery.data} />
    <HorizonTable detail={detail} />
  </>
) : detail.strategy_kind === 'analysis_contract' && detail.event_summary ? (
  ...
) : ...}
```

- [ ] daily rally API가 실패해도 `HorizonTable`은 계속 렌더링한다.
- [ ] 실행: `cd frontend; npm run build`

### Task 8: E2E 수동 검증

- [ ] 백엔드 서버 실행: `.venv/Scripts/python.exe -m uvicorn backend.main:app --reload`
- [ ] 프론트 서버 실행: `cd frontend; npm run dev`
- [ ] 브라우저에서 `/backtest`로 이동한다.
- [ ] `Run Daily 20d +40% Rally` 버튼을 누른다.
- [ ] job 상태가 pending/running으로 보이는지 확인한다.
- [ ] 완료 후 URL이 `/backtest?runId=<daily-rally-run-id>`로 바뀌는지 확인한다.
- [ ] daily rally summary, rules table, candidates table, horizon table이 같은 run id 기준으로 렌더링되는지 확인한다.
- [ ] `/jobs`에서 strategy job label이 `daily_20d_40pct_rally` 또는 사람이 읽을 수 있는 label로 표시되는지 확인한다. 필요하면 `frontend/src/pages/JobsPage.tsx`의 label helper에 `daily rally` label을 추가한다.

## 테스트

필수 실행:

```powershell
cd frontend
npm test -- backtestStrategySelection
npm test -- backtestHighlights
npm run build
```

백엔드 연동 smoke:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_backtest_router.py backend/tests/test_daily_rally_persistence.py -v
```

완료 기준:

- daily rally strategy job을 백테스트 화면에서 시작할 수 있다.
- 기존 polling이 daily rally job 완료도 감지하고 완료 run을 자동 선택한다.
- daily rally run에서 rule insight와 current candidates API를 호출한다.
- 20d/40d/60d/120d forward return 통계가 일 단위 label로 표시된다.
- `npm run build`가 성공한다.
