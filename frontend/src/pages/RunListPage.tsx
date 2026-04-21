import { Link } from 'react-router-dom';
import { useCreateRun, useRuns } from '../hooks/useRuns';
import type { Run } from '../types';

const dateFormatter = new Intl.DateTimeFormat('ko-KR', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
});

function formatRunDate(value: string) {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return dateFormatter.format(date);
}

function getErrorMessage(
  error: unknown,
  fallback = '실행 목록을 불러오지 못했습니다.',
) {
  if (error instanceof Error) {
    return error.message;
  }

  return fallback;
}

function RunSkeleton() {
  return (
    <div className="grid gap-3">
      {[0, 1, 2].map((item) => (
        <div
          className="h-[108px] animate-pulse rounded-lg border border-amber-200/10 bg-slate-900/65"
          key={item}
        />
      ))}
    </div>
  );
}

function RunRow({ run }: { run: Run }) {
  return (
    <Link
      className="group grid gap-4 rounded-lg border border-amber-200/10 bg-slate-900/70 p-5 transition duration-200 hover:border-amber-300/45 hover:bg-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-300 md:grid-cols-[minmax(0,1fr)_140px_96px]"
      to={`/runs/${run.id}`}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-sm font-semibold text-amber-200">
            {formatRunDate(run.created_at)}
          </p>
          <span className="rounded-md border border-slate-700/80 px-2 py-1 text-xs font-medium text-slate-400">
            Run #{run.id}
          </span>
        </div>
        <p className="mt-3 line-clamp-2 text-sm leading-6 text-slate-300">
          {run.memo?.trim() || '메모 없음'}
        </p>
      </div>

      <div className="self-center">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
          analyses
        </p>
        <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-50">
          {run.analysis_count}
        </p>
      </div>

      <div className="flex items-center justify-start text-sm font-semibold text-amber-200 transition group-hover:text-amber-100 md:justify-end">
        열기
        <span aria-hidden className="ml-2 transition group-hover:translate-x-1">
          &gt;
        </span>
      </div>
    </Link>
  );
}

export function RunListPage() {
  const runsQuery = useRuns();
  const createRunMutation = useCreateRun();

  const runs = runsQuery.data ?? [];
  const isCreating = createRunMutation.isPending;

  return (
    <section className="grid gap-6">
      <div className="flex flex-col gap-4 border-b border-amber-200/10 pb-6 md:flex-row md:items-end md:justify-between">
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-amber-300">
            screening runs
          </p>
          <h2 className="text-3xl font-semibold tracking-tight text-slate-50">
            실행 목록
          </h2>
          <p className="max-w-2xl text-sm leading-6 text-slate-300">
            주간 분석 실행을 최신순으로 확인하고, 각 실행의 종목 분석으로
            바로 이동합니다.
          </p>
        </div>

        <button
          className="inline-flex h-11 items-center justify-center rounded-md bg-amber-300 px-4 text-sm font-semibold text-slate-950 transition hover:bg-amber-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-300 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
          disabled={isCreating}
          onClick={() => createRunMutation.mutate({})}
          type="button"
        >
          {isCreating ? '생성 중...' : '새 실행 만들기'}
        </button>
      </div>

      {createRunMutation.isError && (
        <div
          className="rounded-lg border border-red-300/20 bg-red-950/35 px-4 py-3 text-sm text-red-100"
          role="alert"
        >
          {getErrorMessage(createRunMutation.error, '실행 생성에 실패했습니다.')}
        </div>
      )}

      {runsQuery.isLoading && <RunSkeleton />}

      {runsQuery.isError && (
        <div
          className="rounded-lg border border-red-300/20 bg-red-950/35 p-5"
          role="alert"
        >
          <p className="font-semibold text-red-100">
            실행 목록을 불러오지 못했습니다.
          </p>
          <p className="mt-2 text-sm leading-6 text-red-100/80">
            {getErrorMessage(runsQuery.error)}
          </p>
        </div>
      )}

      {runsQuery.isSuccess && runs.length === 0 && (
        <div className="rounded-lg border border-dashed border-amber-200/20 bg-slate-900/45 p-8">
          <p className="text-lg font-semibold text-slate-50">
            아직 생성된 실행이 없습니다.
          </p>
          <p className="mt-2 max-w-xl text-sm leading-6 text-slate-300">
            첫 실행을 만든 뒤 CLI 또는 수동 입력 흐름에서 분석 결과를
            연결하세요.
          </p>
        </div>
      )}

      {runsQuery.isSuccess && runs.length > 0 && (
        <div className="grid gap-3">
          {runs.map((run) => (
            <RunRow key={run.id} run={run} />
          ))}
        </div>
      )}
    </section>
  );
}
