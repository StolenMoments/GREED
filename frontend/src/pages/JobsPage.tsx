import { Link } from 'react-router-dom';
import { useJobs } from '../hooks/useJobs';
import type { Job, JobStatus } from '../types';
import { formatDate } from '../utils/formatDate';

const visibleStatuses: JobStatus[] = ['pending', 'failed'];

const statusStyles: Record<JobStatus, string> = {
  pending: 'border-sky-200/25 bg-sky-400/10 text-sky-100',
  done: 'border-emerald-200/25 bg-emerald-400/10 text-emerald-100',
  failed: 'border-rose-200/25 bg-rose-400/10 text-rose-100',
};

const statusLabels: Record<JobStatus, string> = {
  pending: '실행 중',
  done: '완료',
  failed: '실패',
};

function LoadingRows() {
  return (
    <div className="divide-y divide-amber-100/10 overflow-hidden rounded-lg border border-amber-100/10 bg-slate-950/45">
      {Array.from({ length: 5 }, (_, index) => (
        <div
          className="grid gap-4 px-5 py-5 lg:grid-cols-[5rem_7rem_6rem_7rem_8rem_11rem_minmax(0,1fr)] lg:items-center"
          key={index}
        >
          {Array.from({ length: 7 }, (_, cellIndex) => (
            <div
              className="h-4 animate-pulse rounded bg-slate-800/80"
              key={cellIndex}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-amber-100/10 bg-slate-950/45 px-6 py-12 text-center">
      <p className="text-sm font-semibold text-slate-100">
        실행 중이거나 실패한 Job이 없습니다.
      </p>
      <p className="mt-2 text-sm text-slate-400">
        새 분석을 시작하면 이 목록에서 진행 상태를 확인할 수 있습니다.
      </p>
    </div>
  );
}

function StatusBadge({ status }: { status: JobStatus }) {
  return (
    <span
      className={[
        'inline-flex w-fit rounded-full border px-2.5 py-1 text-xs font-semibold',
        statusStyles[status],
      ].join(' ')}
    >
      {statusLabels[status]}
    </span>
  );
}

function JobRow({ job }: { job: Job }) {
  return (
    <div className="grid gap-4 px-5 py-5 text-sm lg:grid-cols-[5rem_7rem_6rem_7rem_8rem_11rem_minmax(0,1fr)] lg:items-center">
      <div>
        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 lg:hidden">
          job
        </span>
        <p className="mt-1 font-semibold text-slate-100 lg:mt-0">#{job.id}</p>
      </div>

      <div>
        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 lg:hidden">
          ticker
        </span>
        <p className="mt-1 font-semibold text-amber-100 lg:mt-0">{job.ticker}</p>
      </div>

      <div>
        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 lg:hidden">
          run
        </span>
        <Link
          className="mt-1 inline-flex font-medium text-slate-200 transition hover:text-amber-200 lg:mt-0"
          to={`/runs/${job.run_id}`}
        >
          Run #{job.run_id}
        </Link>
      </div>

      <div>
        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 lg:hidden">
          model
        </span>
        <p className="mt-1 text-slate-300 lg:mt-0">{job.model}</p>
      </div>

      <div>
        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 lg:hidden">
          status
        </span>
        <div className="mt-1 lg:mt-0">
          <StatusBadge status={job.status} />
        </div>
      </div>

      <div>
        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 lg:hidden">
          created
        </span>
        <p className="mt-1 whitespace-nowrap text-slate-300 lg:mt-0">
          {formatDate(job.created_at)}
        </p>
      </div>

      <div className="min-w-0">
        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 lg:hidden">
          detail
        </span>
        {job.analysis_id ? (
          <Link
            className="mt-1 inline-flex rounded-md border border-amber-200/20 px-3 py-2 text-sm font-semibold text-amber-100 transition hover:bg-amber-100/10 lg:mt-0"
            to={`/analyses/${job.analysis_id}`}
          >
            분석 보기
          </Link>
        ) : job.error_message ? (
          <p className="mt-1 max-h-16 overflow-hidden break-words text-sm leading-5 text-rose-100/85 lg:mt-0">
            {job.error_message}
          </p>
        ) : (
          <p className="mt-1 text-sm text-slate-500 lg:mt-0">-</p>
        )}
      </div>
    </div>
  );
}

function JobsPage() {
  const { data: jobs = [], isError, isLoading, refetch } = useJobs(visibleStatuses);
  const pendingCount = jobs.filter((job) => job.status === 'pending').length;
  const failedCount = jobs.filter((job) => job.status === 'failed').length;

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 border-b border-amber-100/10 pb-4 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.32em] text-amber-300">
            background jobs
          </p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-50">
            Job 목록
          </h2>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="rounded-full border border-sky-200/25 px-3 py-1.5 font-semibold text-sky-100">
            실행 중 {pendingCount.toLocaleString('ko-KR')}
          </span>
          <span className="rounded-full border border-rose-200/25 px-3 py-1.5 font-semibold text-rose-100">
            실패 {failedCount.toLocaleString('ko-KR')}
          </span>
        </div>
      </div>

      {isError ? (
        <div className="rounded-lg border border-rose-200/20 bg-rose-950/20 px-6 py-5">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-sm font-semibold text-rose-100">
                Job 목록을 불러오지 못했습니다.
              </p>
              <p className="mt-1 text-sm text-rose-100/70">
                백엔드 응답 상태를 확인한 뒤 다시 시도하세요.
              </p>
            </div>
            <button
              className="w-fit rounded-md border border-rose-100/25 px-4 py-2 text-sm font-semibold text-rose-50 transition hover:bg-rose-100/10"
              onClick={() => void refetch()}
              type="button"
            >
              다시 시도
            </button>
          </div>
        </div>
      ) : isLoading ? (
        <LoadingRows />
      ) : jobs.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="overflow-hidden rounded-lg border border-amber-100/10 bg-slate-950/45 shadow-2xl shadow-slate-950/30">
          <div className="hidden grid-cols-[5rem_7rem_6rem_7rem_8rem_11rem_minmax(0,1fr)] gap-4 border-b border-amber-100/10 bg-slate-950/80 px-5 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 lg:grid">
            <span>job</span>
            <span>ticker</span>
            <span>run</span>
            <span>model</span>
            <span>status</span>
            <span>created</span>
            <span>detail</span>
          </div>
          <div className="divide-y divide-amber-100/10">
            {jobs.map((job) => (
              <JobRow job={job} key={job.id} />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

export default JobsPage;
