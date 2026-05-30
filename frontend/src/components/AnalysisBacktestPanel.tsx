import { Link } from 'react-router-dom';
import {
  useAnalysisBacktestJobs,
  useTriggerAnalysisBacktest,
} from '../hooks/useAnalysisBacktests';
import type { AnalysisBacktestJob } from '../types';

function isActive(job: AnalysisBacktestJob | undefined): boolean {
  return job?.status === 'pending' || job?.status === 'running';
}

function statusLabel(job: AnalysisBacktestJob | undefined): string {
  if (!job) return 'Not run';
  if (job.status === 'pending') return 'Queued';
  if (job.status === 'running') return 'Running';
  if (job.status === 'done') return 'Done';
  return 'Failed';
}

function statusTone(job: AnalysisBacktestJob | undefined): string {
  if (!job) return 'border-slate-800 text-slate-500';
  if (job.status === 'pending' || job.status === 'running') {
    return 'border-amber-300/30 text-amber-100';
  }
  if (job.status === 'done') return 'border-emerald-300/30 text-emerald-100';
  return 'border-rose-300/30 text-rose-100';
}

function compactError(message: string): string {
  return message.length > 120 ? `${message.slice(0, 117)}...` : message;
}

export default function AnalysisBacktestPanel({
  analysisId,
}: {
  analysisId: number;
}) {
  const jobsQuery = useAnalysisBacktestJobs(analysisId);
  const trigger = useTriggerAnalysisBacktest(analysisId);
  const jobs = jobsQuery.data ?? [];
  const latest = jobs[0];
  const isRunning = jobs.some(isActive) || trigger.isPending;

  async function handleRun() {
    try {
      await trigger.mutateAsync({ similarity_threshold: 12 });
    } catch {
      // The mutation state renders the failure message below.
    }
  }

  return (
    <aside className="rounded-lg border border-amber-100/10 bg-slate-950/55 p-6">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-slate-100">
            KOSPI200 Contract Backtest
          </h3>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            Runs the analysis contract against similar KOSPI200 history using the fixed 12+ threshold.
          </p>
        </div>
        <span
          className={`shrink-0 rounded-full border px-3 py-1 text-xs font-semibold ${statusTone(latest)}`}
        >
          12+ · {statusLabel(latest)}
        </span>
      </div>

      <button
        className="mt-5 h-10 w-full rounded-md bg-amber-300 px-4 text-sm font-semibold text-slate-950 transition hover:bg-amber-200 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70"
        disabled={isRunning}
        onClick={() => void handleRun()}
        type="button"
      >
        {isRunning ? '12+ running' : 'Run 12+ backtest'}
      </button>

      {trigger.isError ? (
        <p className="mt-3 rounded-md border border-rose-300/20 bg-rose-950/20 px-3 py-2 text-xs leading-5 text-rose-100">
          Could not start the backtest job.
        </p>
      ) : null}

      {jobsQuery.isError ? (
        <p className="mt-3 rounded-md border border-rose-300/20 bg-rose-950/20 px-3 py-2 text-xs leading-5 text-rose-100">
          Could not load recent backtest jobs.
        </p>
      ) : null}

      {latest?.status === 'failed' && latest.error_message ? (
        <p className="mt-3 rounded-md border border-rose-300/20 bg-rose-950/20 px-3 py-2 text-xs leading-5 text-rose-100">
          {compactError(latest.error_message)}
        </p>
      ) : null}

      {latest?.status === 'done' && latest.backtest_run_id ? (
        <Link
          className="mt-4 block rounded-md border border-emerald-300/25 px-3 py-2 text-center text-sm font-semibold text-emerald-100 transition hover:bg-emerald-300/10"
          to={`/backtest?runId=${latest.backtest_run_id}`}
        >
          Backtest Run #{latest.backtest_run_id}
          <span className="ml-2 text-xs font-medium text-emerald-200/70">12+</span>
        </Link>
      ) : null}

      <div className="mt-4 border-t border-amber-100/10 pt-3">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs font-medium text-slate-500">Recent runs</p>
          {jobsQuery.isFetching ? (
            <span className="text-xs text-slate-600">Refreshing</span>
          ) : null}
        </div>

        {jobs.length === 0 ? (
          <p className="mt-2 text-xs leading-5 text-slate-500">
            No contract backtests have been run yet.
          </p>
        ) : (
          <div className="mt-2 space-y-1.5">
            {jobs.slice(0, 4).map((job) => (
              <div
                className="flex items-center justify-between gap-2 text-xs text-slate-500"
                key={job.id}
              >
                <span className="min-w-0 truncate">
                  #{job.id} · {job.similarity_threshold}+
                </span>
                {job.backtest_run_id ? (
                  <Link
                    className="shrink-0 text-amber-100 transition hover:text-amber-200"
                    to={`/backtest?runId=${job.backtest_run_id}`}
                  >
                    run #{job.backtest_run_id}
                  </Link>
                ) : (
                  <span
                    className={`shrink-0 rounded-full border px-2 py-0.5 font-semibold ${statusTone(job)}`}
                  >
                    {statusLabel(job)}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
