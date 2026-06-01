import type { BacktestStrategyJob } from '../api/backtest';

export interface CompletedStrategySelectionState {
  hydrated: boolean;
  appliedJobId: number | null;
}

export function nextCompletedStrategySelection(
  state: CompletedStrategySelectionState,
  latestJob: Pick<BacktestStrategyJob, 'id' | 'status' | 'backtest_run_id'> | undefined,
): { state: CompletedStrategySelectionState; runId: number | null } {
  if (!latestJob) {
    return { state, runId: null };
  }

  const completedRunId =
    latestJob.status === 'done' ? latestJob.backtest_run_id : null;

  if (!state.hydrated) {
    return {
      state: {
        hydrated: true,
        appliedJobId: completedRunId === null ? null : latestJob.id,
      },
      runId: null,
    };
  }

  if (completedRunId === null || state.appliedJobId === latestJob.id) {
    return { state, runId: null };
  }

  return {
    state: { hydrated: true, appliedJobId: latestJob.id },
    runId: completedRunId,
  };
}
