import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  createBacktestStrategyJob,
  fetchBacktestRun,
  fetchBacktestRuns,
  fetchBacktestStrategyJobs,
  fetchDailyRallyCandidates,
  fetchDailyRallyInsights,
  fetchDailyRallyPatternStats,
  fetchDailyRallyValidation,
  type BacktestRunDetail,
  type BacktestRunSummary,
  type BacktestStat,
  type BacktestStrategyJob,
} from '../api/backtest';
import {
  DailyRallyCandidateBriefing,
  DailyRallyCandidatesTable,
  DailyRallyPatternBriefing,
  DailyRallyPatternStatsTable,
  DailyRallyRulesTable,
  DailyRallySummaryPanel,
  DailyRallyValidationPanel,
} from './DailyRallyPanels';
import { formatHorizonLabel, formatScoreBucketLabel } from './backtestHighlights';
import {
  nextCompletedStrategySelection,
  type CompletedStrategySelectionState,
} from './backtestStrategySelection';

const DAILY_RALLY_KIND = 'daily_20d_40pct_rally';
const DAILY_HORIZONS = [20, 40, 60, 120] as const;
const DAILY_BUCKETS = ['positive', 'control', 'ALL'] as const;

function ratio(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return '--';
  return `${(value * 100).toFixed(digits)}%`;
}

function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return '--';
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(digits)}%`;
}

function count(value: number | null | undefined): string {
  if (value === null || value === undefined) return '--';
  return value.toLocaleString('ko-KR');
}

function date(value: string | null | undefined): string {
  if (!value) return '--';
  return new Date(value).toLocaleDateString('ko-KR');
}

function statOf(
  stats: BacktestStat[],
  horizon: number,
  bucket: string,
): BacktestStat | undefined {
  return stats.find((stat) => stat.horizon === horizon && stat.score_bucket === bucket);
}

function signedTone(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'text-slate-500';
  return value >= 0 ? 'text-emerald-300' : 'text-rose-300';
}

function LoadingBlock({ className = 'h-40' }: { className?: string }) {
  return (
    <div
      className={`${className} animate-pulse rounded-lg border border-amber-100/10 bg-slate-950/60`}
    />
  );
}

function ErrorPanel({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-lg border border-rose-200/20 bg-rose-950/20 px-6 py-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-rose-100">
            Daily Rally 데이터를 불러오지 못했습니다.
          </p>
          <p className="mt-1 text-sm text-rose-100/70">
            백엔드 응답 상태를 확인한 뒤 다시 시도하세요.
          </p>
        </div>
        <button
          className="rounded-md border border-rose-100/25 px-4 py-2 text-sm font-semibold text-rose-50 transition hover:bg-rose-100/10"
          onClick={onRetry}
          type="button"
        >
          다시 시도
        </button>
      </div>
    </div>
  );
}

function EmptyState({ onRun, isStarting }: { onRun: () => void; isStarting: boolean }) {
  return (
    <div className="rounded-lg border border-amber-100/10 bg-slate-950/45 px-6 py-12 text-center">
      <p className="text-sm font-semibold text-slate-100">
        Daily 20d +40% Rally 분석 실행 결과가 없습니다.
      </p>
      <p className="mt-2 text-sm text-slate-400">
        KOSPI200 일봉 데이터에서 급등 전 반복 패턴을 채굴하려면 새 실행을 시작하세요.
      </p>
      <button
        className="mt-6 rounded-md border border-amber-200/40 bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-amber-200 disabled:cursor-not-allowed disabled:border-slate-700 disabled:bg-slate-900 disabled:text-slate-500"
        disabled={isStarting}
        onClick={onRun}
        type="button"
      >
        {isStarting ? 'Starting...' : 'Run Daily Rally'}
      </button>
    </div>
  );
}

function RunSelector({
  runId,
  runs,
  onChange,
}: {
  runId: number | null;
  runs: BacktestRunSummary[];
  onChange: (id: number) => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-slate-800 bg-slate-950/45 px-5 py-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.28em] text-amber-300">
          analysis run
        </p>
        <p className="mt-2 text-sm text-slate-400">
          완료된 Daily Rally 실행 중 하나를 선택합니다.
        </p>
      </div>
      <select
        className="min-w-[360px] rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 transition focus:outline-none focus:ring-1 focus:ring-amber-400/60"
        value={runId ?? ''}
        onChange={(event) => onChange(Number(event.target.value))}
      >
        {runs.map((run) => (
          <option key={run.id} value={run.id}>
            #{run.id} · {date(run.created_at)} · signals {run.signal_count.toLocaleString('ko-KR')}
          </option>
        ))}
      </select>
    </div>
  );
}

function StrategyBar({
  latestJob,
  isStarting,
  onRun,
}: {
  latestJob: BacktestStrategyJob | undefined;
  isStarting: boolean;
  onRun: () => void;
}) {
  const isRunning = latestJob?.status === 'pending' || latestJob?.status === 'running';
  const disabled = isRunning || isStarting;
  const statusLabel = latestJob
    ? latestJob.status === 'done' && latestJob.backtest_run_id !== null
      ? `done · Backtest #${latestJob.backtest_run_id}`
      : latestJob.status
    : 'ready';

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-amber-100/10 bg-slate-950/45 px-5 py-4 md:flex-row md:items-center md:justify-between">
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-[0.28em] text-amber-300">
          strategy job
        </p>
        <p className="mt-2 text-sm text-slate-300">
          20거래일 내 +40% 급등 이벤트를 라벨링하고, 급등 전 조건 조합을 다시 채굴합니다.
        </p>
        {latestJob?.status === 'failed' && latestJob.error_message && (
          <p className="mt-2 max-w-3xl truncate text-sm font-semibold text-rose-200">
            {latestJob.error_message}
          </p>
        )}
      </div>
      <div className="flex items-center gap-3">
        <span className="rounded-full border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300">
          {statusLabel}
        </span>
        <button
          className={[
            'rounded-md px-4 py-2 text-sm font-semibold transition',
            disabled
              ? 'cursor-not-allowed border border-slate-700 bg-slate-900 text-slate-500'
              : 'border border-amber-200/40 bg-amber-300 text-slate-950 hover:bg-amber-200',
          ].join(' ')}
          disabled={disabled}
          onClick={onRun}
          type="button"
        >
          {isStarting ? 'Starting...' : 'Run Daily Rally'}
        </button>
      </div>
    </div>
  );
}

function ForwardReturnTable({ detail }: { detail: BacktestRunDetail }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950/45">
      <table className="w-full min-w-[920px] border-collapse text-sm">
        <thead>
          <tr className="text-slate-400">
            <th className="px-4 py-3 text-left">구분</th>
            {DAILY_HORIZONS.map((horizon) => (
              <th className="px-4 py-3 text-right" key={horizon}>
                {formatHorizonLabel(detail, horizon)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {DAILY_BUCKETS.map((bucket) => (
            <tr className="border-t border-slate-800/70" key={bucket}>
              <td className="px-4 py-3 font-semibold text-slate-200">
                {formatScoreBucketLabel(bucket)}
              </td>
              {DAILY_HORIZONS.map((horizon) => {
                const stat = statOf(detail.stats, horizon, bucket);
                return (
                  <td className="px-4 py-3 text-right" key={`${bucket}:${horizon}`}>
                    <div className="flex flex-col gap-1">
                      <span className={`font-semibold ${signedTone(stat?.mean)}`}>
                        {pct(stat?.mean)}
                      </span>
                      <span className="text-xs text-slate-500">
                        win {ratio(stat?.win_rate)} · n {count(stat?.count)}
                      </span>
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DailyRallyPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const runIdParam = searchParams.get('runId');
  const requestedRunId = runIdParam === null ? NaN : Number(runIdParam);
  const [runId, setRunId] = useState<number | null>(null);
  const completedStrategySelectionRef = useRef<CompletedStrategySelectionState>({
    hydrated: false,
    appliedJobId: null,
  });

  const {
    data: allRuns = [],
    isError: runsError,
    isLoading: runsLoading,
    refetch: refetchRuns,
  } = useQuery({
    queryKey: ['backtest', 'runs'],
    queryFn: fetchBacktestRuns,
  });
  const runs = useMemo(
    () => allRuns.filter((run) => run.strategy_kind === DAILY_RALLY_KIND),
    [allRuns],
  );

  const { data: strategyJobs = [] } = useQuery({
    queryKey: ['backtest', 'strategy-jobs'],
    queryFn: fetchBacktestStrategyJobs,
    refetchInterval: (query) => {
      const jobs = query.state.data;
      return jobs?.some((job) => job.status === 'pending' || job.status === 'running') ? 2000 : false;
    },
  });
  const latestDailyRallyJob = strategyJobs.find((job) => job.strategy_kind === DAILY_RALLY_KIND);
  const runDailyRallyMutation = useMutation({
    mutationFn: () => createBacktestStrategyJob(DAILY_RALLY_KIND),
    onSuccess: (job) => {
      queryClient.setQueryData(['backtest', 'strategy-jobs'], (current: BacktestStrategyJob[] | undefined) => [
        job,
        ...(current ?? []).filter((item) => item.id !== job.id),
      ]);
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });

  useEffect(() => {
    if (runs.length === 0) {
      setRunId(null);
      return;
    }
    const requested = Number.isInteger(requestedRunId)
      ? runs.find((run) => run.id === requestedRunId)
      : undefined;
    setRunId((current) => {
      if (current !== null && runs.some((run) => run.id === current)) return current;
      return requested?.id ?? runs[0].id;
    });
  }, [requestedRunId, runs]);

  useEffect(() => {
    const selection = nextCompletedStrategySelection(
      completedStrategySelectionRef.current,
      latestDailyRallyJob,
    );
    completedStrategySelectionRef.current = selection.state;

    if (selection.runId === null) {
      return;
    }

    void queryClient.invalidateQueries({ queryKey: ['backtest', 'runs'] });
    setRunId(selection.runId);
    navigate(`/daily-rally?runId=${selection.runId}`, { replace: true });
  }, [latestDailyRallyJob, navigate, queryClient]);

  const {
    data: detail,
    isError: detailError,
    isLoading: detailLoading,
    refetch: refetchDetail,
  } = useQuery({
    queryKey: ['backtest', 'run', runId],
    queryFn: () => fetchBacktestRun(runId as number),
    enabled: runId !== null,
  });
  const dailyRallyInsightsQuery = useQuery({
    queryKey: ['backtest', 'run', runId, 'daily-rally-insights'],
    queryFn: () => fetchDailyRallyInsights(runId as number),
    enabled: runId !== null,
  });
  const dailyRallyCandidatesQuery = useQuery({
    queryKey: ['backtest', 'run', runId, 'daily-rally-candidates'],
    queryFn: () => fetchDailyRallyCandidates(runId as number),
    enabled: runId !== null,
  });
  const dailyRallyPatternStatsQuery = useQuery({
    queryKey: ['backtest', 'run', runId, 'daily-rally-pattern-stats'],
    queryFn: () => fetchDailyRallyPatternStats(runId as number),
    enabled: runId !== null,
  });
  const dailyRallyValidationQuery = useQuery({
    queryKey: ['backtest', 'run', runId, 'daily-rally-validation'],
    queryFn: () => fetchDailyRallyValidation(runId as number),
    enabled: runId !== null,
  });

  const setSelectedRun = (id: number) => {
    setRunId(id);
    navigate(`/daily-rally?runId=${id}`, { replace: true });
  };

  const retry = () => {
    void refetchRuns();
    if (runId !== null) void refetchDetail();
    void dailyRallyInsightsQuery.refetch();
    void dailyRallyCandidatesQuery.refetch();
    void dailyRallyPatternStatsQuery.refetch();
    void dailyRallyValidationQuery.refetch();
  };

  return (
    <section className="flex flex-col gap-8">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-amber-100/10 pb-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.32em] text-amber-300">
            daily rally
          </p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-50">
            20거래일 +40% 급등 패턴
          </h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-400">
            과거 급등 이벤트 직전의 일봉·주봉 조건을 채굴하고, 현재 같은 조건을 만족하는
            종목을 확인합니다.
          </p>
        </div>
        {runId !== null && (
          <Link
            className="rounded-md border border-slate-700 px-3 py-2 text-sm font-semibold text-slate-300 transition hover:border-amber-200/50 hover:text-amber-200"
            to={`/backtest?runId=${runId}`}
          >
            Backtest #{runId}
          </Link>
        )}
      </div>

      <StrategyBar
        isStarting={runDailyRallyMutation.isPending}
        latestJob={latestDailyRallyJob}
        onRun={() => runDailyRallyMutation.mutate()}
      />

      {runsError || detailError ? (
        <ErrorPanel onRetry={retry} />
      ) : runsLoading ? (
        <LoadingBlock className="h-16" />
      ) : runs.length === 0 ? (
        <EmptyState
          isStarting={runDailyRallyMutation.isPending}
          onRun={() => runDailyRallyMutation.mutate()}
        />
      ) : (
        <>
          <RunSelector runId={runId} runs={runs} onChange={setSelectedRun} />

          {detailLoading || !detail ? (
            <div className="flex flex-col gap-4">
              <LoadingBlock className="h-28" />
              <LoadingBlock className="h-64" />
            </div>
          ) : (
            <>
              <DailyRallySummaryPanel
                candidates={dailyRallyCandidatesQuery.data}
                detail={detail}
                insights={dailyRallyInsightsQuery.data}
                isLoading={dailyRallyInsightsQuery.isLoading || dailyRallyCandidatesQuery.isLoading}
              />
              <DailyRallyPatternBriefing
                insights={dailyRallyInsightsQuery.data}
                isError={dailyRallyInsightsQuery.isError}
                patternStats={dailyRallyPatternStatsQuery.data}
                patternStatsIsError={dailyRallyPatternStatsQuery.isError}
              />
              <DailyRallyCandidateBriefing
                candidates={dailyRallyCandidatesQuery.data}
                isError={dailyRallyCandidatesQuery.isError}
              />
              <DailyRallyValidationPanel
                isError={dailyRallyValidationQuery.isError}
                validation={dailyRallyValidationQuery.data}
              />
              <ForwardReturnTable detail={detail} />
              <DailyRallyPatternStatsTable
                isError={dailyRallyPatternStatsQuery.isError}
                patternStats={dailyRallyPatternStatsQuery.data}
              />
              <DailyRallyRulesTable
                insights={dailyRallyInsightsQuery.data}
                isError={dailyRallyInsightsQuery.isError}
              />
              <DailyRallyCandidatesTable
                candidates={dailyRallyCandidatesQuery.data}
                isError={dailyRallyCandidatesQuery.isError}
              />
            </>
          )}
        </>
      )}
    </section>
  );
}

export default DailyRallyPage;
