import { useNavigate } from 'react-router-dom';
import { useCreateRun, useRuns } from '../hooks/useRuns';
import type { Run } from '../types';
import { formatDate } from '../utils/formatDate';

function LoadingRows() {
  return (
    <div className="divide-y divide-amber-100/10 overflow-hidden rounded-lg border border-amber-100/10 bg-slate-950/45">
      {Array.from({ length: 5 }, (_, index) => (
        <div
          className="grid gap-4 px-5 py-5 md:grid-cols-[1fr_9rem_7rem] md:items-center md:gap-5"
          key={index}
        >
          <div className="space-y-3">
            <div className="h-4 w-36 animate-pulse rounded bg-slate-700/60" />
            <div className="h-3 w-64 animate-pulse rounded bg-slate-800/80" />
          </div>
          <div className="h-4 w-24 animate-pulse rounded bg-slate-800/80" />
          <div className="h-7 w-20 animate-pulse rounded-full bg-slate-800/80" />
        </div>
      ))}
    </div>
  );
}

function EmptyState({
  onCreateRun,
  isCreating,
}: {
  onCreateRun: () => void;
  isCreating: boolean;
}) {
  return (
    <div className="rounded-lg border border-amber-100/10 bg-slate-950/45 px-6 py-12 text-center">
      <p className="text-sm font-semibold text-slate-100">
        아직 생성된 실행이 없습니다.
      </p>
      <p className="mt-2 text-sm text-slate-400">
        새 실행을 만들고 종목 분석 흐름을 시작하세요.
      </p>
      <button
        className="mt-6 rounded-md bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-amber-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70 disabled:cursor-not-allowed disabled:opacity-60"
        disabled={isCreating}
        onClick={onCreateRun}
        type="button"
      >
        {isCreating ? '생성 중' : '새 실행 만들기'}
      </button>
    </div>
  );
}

function RunRow({ run, onSelect }: { run: Run; onSelect: () => void }) {
  const memo = run.memo?.trim();

  return (
    <button
      aria-label={`실행 ${run.id} 상세 보기`}
      className="grid w-full gap-4 px-5 py-5 text-left transition hover:bg-amber-100/[0.035] focus:outline-none focus-visible:bg-amber-100/[0.05] focus-visible:ring-2 focus-visible:ring-amber-300/70 md:grid-cols-[1fr_9rem_7rem] md:items-center md:gap-5"
      onClick={onSelect}
      type="button"
    >
      <span className="min-w-0">
        <span className="flex flex-wrap items-center gap-3">
          <span className="text-base font-semibold text-slate-50">
            Run #{run.id}
          </span>
          <span className="rounded-full border border-amber-200/20 px-2.5 py-1 text-xs font-semibold text-amber-100">
            {run.analysis_count.toLocaleString('ko-KR')}개 분석
          </span>
        </span>
        <span className="mt-2 block truncate text-sm leading-6 text-slate-400">
          {memo || '메모 없음'}
        </span>
      </span>

      <span className="text-sm font-medium text-slate-300">
        {formatDate(run.created_at)}
      </span>

      <span className="w-fit rounded-md border border-slate-700/80 px-3 py-2 text-sm font-semibold text-slate-200 transition md:justify-self-end">
        열기
      </span>
    </button>
  );
}

function RunListPage() {
  const { data: runs = [], isError, isLoading, refetch } = useRuns();
  const createRun = useCreateRun();
  const navigate = useNavigate();

  function handleCreateRun() {
    createRun.mutate(
      {},
      {
        onSuccess: (run) => {
          navigate(`/runs/${run.id}`);
        },
      },
    );
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 border-b border-amber-100/10 pb-4 md:flex-row md:items-end md:justify-between md:gap-6">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.32em] text-amber-300">
            screening runs
          </p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-50">
            실행 목록
          </h2>
        </div>

        <button
          className="w-fit shrink-0 rounded-md bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-amber-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70 disabled:cursor-not-allowed disabled:opacity-60"
          disabled={createRun.isPending}
          onClick={handleCreateRun}
          type="button"
        >
          {createRun.isPending ? '생성 중' : '새 실행 만들기'}
        </button>
      </div>

      {createRun.isError ? (
        <div className="rounded-lg border border-rose-200/20 bg-rose-950/20 px-6 py-5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-rose-100">
                새 실행을 만들지 못했습니다.
              </p>
              <p className="mt-1 text-sm text-rose-100/70">
                백엔드 응답 상태를 확인한 뒤 다시 시도하세요.
              </p>
            </div>
            <button
              className="rounded-md border border-rose-100/25 px-4 py-2 text-sm font-semibold text-rose-50 transition hover:bg-rose-100/10"
              onClick={handleCreateRun}
              type="button"
            >
              다시 시도
            </button>
          </div>
        </div>
      ) : null}

      {isError ? (
        <div className="rounded-lg border border-rose-200/20 bg-rose-950/20 px-6 py-5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-rose-100">
                실행 목록을 불러오지 못했습니다.
              </p>
              <p className="mt-1 text-sm text-rose-100/70">
                백엔드 응답 상태를 확인한 뒤 다시 시도하세요.
              </p>
            </div>
            <button
              className="rounded-md border border-rose-100/25 px-4 py-2 text-sm font-semibold text-rose-50 transition hover:bg-rose-100/10"
              onClick={() => void refetch()}
              type="button"
            >
              다시 시도
            </button>
          </div>
        </div>
      ) : isLoading ? (
        <LoadingRows />
      ) : runs.length === 0 ? (
        <EmptyState
          isCreating={createRun.isPending}
          onCreateRun={handleCreateRun}
        />
      ) : (
        <div className="overflow-hidden rounded-lg border border-amber-100/10 bg-slate-950/45 shadow-2xl shadow-slate-950/30">
          <div className="hidden grid-cols-[1fr_9rem_7rem] gap-5 border-b border-amber-100/10 bg-slate-950/80 px-5 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 md:grid">
            <span>run / memo</span>
            <span>created</span>
            <span className="text-right">action</span>
          </div>
          <div className="divide-y divide-amber-100/10">
            {runs.map((run) => (
              <RunRow key={run.id} run={run} onSelect={() => navigate(`/runs/${run.id}`)} />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

export default RunListPage;
