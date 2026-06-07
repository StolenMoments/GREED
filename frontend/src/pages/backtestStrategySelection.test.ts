import { nextCompletedStrategySelection } from './backtestStrategySelection';

const hydrated = nextCompletedStrategySelection(
  { hydrated: false, appliedJobId: null },
  { id: 34, status: 'done', backtest_run_id: 34 },
);

if (hydrated.runId !== null) {
  throw new Error(`Initial completed job should not be selected, received run ${hydrated.runId}`);
}

const completed = nextCompletedStrategySelection(
  hydrated.state,
  { id: 35, status: 'done', backtest_run_id: 36 },
);

if (completed.runId !== 36) {
  throw new Error(`Newly completed job should select run 36, received ${completed.runId}`);
}

const repeated = nextCompletedStrategySelection(completed.state, {
  id: 35,
  status: 'done',
  backtest_run_id: 36,
});

if (repeated.runId !== null) {
  throw new Error(`Already applied job should not be selected again, received ${repeated.runId}`);
}

const pending = nextCompletedStrategySelection(
  { hydrated: false, appliedJobId: null },
  { id: 36, status: 'pending', backtest_run_id: null },
);
const finishedPending = nextCompletedStrategySelection(pending.state, {
  id: 36,
  status: 'done',
  backtest_run_id: 37,
});

if (finishedPending.runId !== 37) {
  throw new Error(`Observed pending job should select run 37 when done, received ${finishedPending.runId}`);
}

const dailyRallyPending = nextCompletedStrategySelection(
  { hydrated: false, appliedJobId: null },
  {
    id: 40,
    strategy_kind: 'daily_20d_40pct_rally',
    status: 'pending',
    backtest_run_id: null,
  },
);
const finishedDailyRally = nextCompletedStrategySelection(dailyRallyPending.state, {
  id: 40,
  strategy_kind: 'daily_20d_40pct_rally',
  status: 'done',
  backtest_run_id: 41,
});

if (finishedDailyRally.runId !== 41) {
  throw new Error(
    `Daily rally completed job should select run 41, received ${finishedDailyRally.runId}`,
  );
}
