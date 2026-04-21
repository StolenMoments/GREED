import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { FormEvent, useEffect, useMemo, useState } from 'react';
import { judgmentStyles } from '../constants/analysisStyles';
import { useAllAnalyses } from '../hooks/useAnalyses';
import type { AnalysisFilters, AnalysisSummary, Judgment } from '../types';
import { formatDate } from '../utils/formatDate';

const judgmentTabs: Array<{ label: string; value?: Judgment }> = [
  { label: '전체' },
  { label: '매수', value: '매수' },
  { label: '홀드', value: '홀드' },
  { label: '관망', value: '관망' },
  { label: '매도', value: '매도' },
];

function isValidJudgment(value: string | null): value is Judgment {
  return judgmentTabs.some((tab) => tab.value === value);
}

function parseRunId(value: string | null) {
  if (!value) {
    return undefined;
  }

  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function LoadingRows() {
  return (
    <div className="divide-y divide-amber-100/10 overflow-hidden rounded-lg border border-amber-100/10 bg-slate-950/45">
      {Array.from({ length: 7 }, (_, index) => (
        <div
          className="grid gap-4 px-5 py-4 xl:grid-cols-[9rem_1.1fr_0.55fr_0.8fr_6rem] xl:items-center"
          key={index}
        >
          <div className="h-4 w-28 animate-pulse rounded bg-slate-800/80" />
          <div className="space-y-2">
            <div className="h-4 w-32 animate-pulse rounded bg-slate-700/60" />
            <div className="h-3 w-44 animate-pulse rounded bg-slate-800/80" />
          </div>
          <div className="h-7 w-14 animate-pulse rounded-full bg-slate-800/80" />
          <div className="h-4 w-24 animate-pulse rounded bg-slate-800/80" />
          <div className="h-4 w-16 animate-pulse rounded bg-slate-800/80" />
        </div>
      ))}
    </div>
  );
}

function EmptyState({
  hasFilters,
  onClear,
}: {
  hasFilters: boolean;
  onClear: () => void;
}) {
  return (
    <div className="rounded-lg border border-amber-100/10 bg-slate-950/45 px-6 py-12 text-center">
      <p className="text-sm font-semibold text-slate-100">
        조건에 맞는 분석이 없습니다.
      </p>
      <p className="mt-2 text-sm text-slate-400">
        {hasFilters
          ? '필터를 조정해 다른 분석을 확인하세요.'
          : '분석이 저장되면 최신 항목부터 여기에 표시됩니다.'}
      </p>
      {hasFilters ? (
        <button
          className="mt-6 rounded-md border border-amber-200/20 px-4 py-2 text-sm font-semibold text-amber-100 transition hover:bg-amber-100/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70"
          onClick={onClear}
          type="button"
        >
          필터 초기화
        </button>
      ) : null}
    </div>
  );
}

function AnalysisRow({
  analysis,
  onSelect,
}: {
  analysis: AnalysisSummary;
  onSelect: () => void;
}) {
  return (
    <button
      aria-label={`${analysis.name} (${analysis.ticker}) 분석 상세 보기`}
      className="grid w-full gap-4 px-5 py-4 text-left transition hover:bg-amber-100/[0.035] focus:outline-none focus-visible:bg-amber-100/[0.05] focus-visible:ring-2 focus-visible:ring-amber-300/70 xl:grid-cols-[9rem_1.1fr_0.55fr_0.8fr_6rem] xl:items-center"
      onClick={onSelect}
      type="button"
    >
      <span className="text-sm font-medium text-slate-300">
        {formatDate(analysis.created_at)}
      </span>

      <span className="min-w-0">
        <span className="block truncate text-base font-semibold text-slate-50">
          {analysis.name}
        </span>
        <span className="mt-1 flex flex-wrap items-center gap-2 text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
          <span>{analysis.ticker}</span>
          <span className="text-slate-700">/</span>
          <span>run #{analysis.run_id}</span>
        </span>
      </span>

      <span
        className={[
          'w-fit rounded-full border px-3 py-1 text-xs font-semibold',
          judgmentStyles[analysis.judgment],
        ].join(' ')}
      >
        {analysis.judgment}
      </span>

      <span className="truncate text-sm font-medium text-slate-300">
        {analysis.model}
      </span>

      <span className="w-fit rounded-md border border-slate-700/80 px-3 py-2 text-sm font-semibold text-slate-200 transition xl:justify-self-end">
        열기
      </span>
    </button>
  );
}

function AnalysisListPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedJudgment = searchParams.get('judgment');
  const activeJudgment = isValidJudgment(requestedJudgment)
    ? requestedJudgment
    : undefined;
  const activeRunId = parseRunId(searchParams.get('run_id'));
  const [runIdInput, setRunIdInput] = useState(
    activeRunId ? String(activeRunId) : '',
  );
  const filters = useMemo<AnalysisFilters>(
    () => ({
      ...(activeJudgment ? { judgment: activeJudgment } : {}),
      ...(activeRunId ? { run_id: activeRunId } : {}),
    }),
    [activeJudgment, activeRunId],
  );
  const {
    data: analyses = [],
    isError,
    isLoading,
    refetch,
  } = useAllAnalyses(filters);
  const hasFilters = Boolean(activeJudgment || activeRunId);

  useEffect(() => {
    setRunIdInput(activeRunId ? String(activeRunId) : '');
  }, [activeRunId]);

  function updateFilters(next: AnalysisFilters) {
    const params = new URLSearchParams();

    if (next.judgment) {
      params.set('judgment', next.judgment);
    }

    if (next.run_id) {
      params.set('run_id', String(next.run_id));
    }

    setSearchParams(params);
  }

  function handleJudgmentChange(judgment?: Judgment) {
    updateFilters({
      ...(judgment ? { judgment } : {}),
      ...(activeRunId ? { run_id: activeRunId } : {}),
    });
  }

  function handleRunFilterSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextRunId = parseRunId(runIdInput);

    if (!nextRunId) {
      setRunIdInput('');
    }

    updateFilters({
      ...(activeJudgment ? { judgment: activeJudgment } : {}),
      ...(nextRunId ? { run_id: nextRunId } : {}),
    });
  }

  function handleClearFilters() {
    setRunIdInput('');
    setSearchParams({});
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-4 border-b border-amber-100/10 pb-4 xl:flex-row xl:items-end xl:justify-between xl:gap-6">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.32em] text-amber-300">
            global analyses
          </p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-50">
            전체 분석 목록
          </h2>
        </div>

        <div className="flex flex-col gap-3 xl:items-end">
          <div
            className="flex w-fit items-center rounded-lg border border-amber-100/10 bg-slate-950/70 p-1"
            role="tablist"
          >
            {judgmentTabs.map((tab) => {
              const isActive = tab.value === activeJudgment;

              return (
                <button
                  aria-selected={isActive}
                  className={[
                    'min-w-16 rounded-md px-4 py-2 text-sm font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70',
                    isActive
                      ? 'bg-amber-300 text-slate-950'
                      : 'text-slate-300 hover:bg-slate-800 hover:text-slate-50',
                  ].join(' ')}
                  key={tab.label}
                  onClick={() => handleJudgmentChange(tab.value)}
                  role="tab"
                  type="button"
                >
                  {tab.label}
                </button>
              );
            })}
          </div>

          <form
            className="flex flex-wrap items-center gap-2"
            onSubmit={handleRunFilterSubmit}
          >
            <label
              className="text-sm font-medium text-slate-400"
              htmlFor="run-id-filter"
            >
              실행 ID
            </label>
            <input
              className="h-10 w-28 rounded-md border border-slate-700/80 bg-slate-950/70 px-3 text-sm font-medium text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-amber-300/50 focus:ring-2 focus:ring-amber-300/20"
              id="run-id-filter"
              min={1}
              onChange={(event) => setRunIdInput(event.target.value)}
              placeholder="예: 12"
              type="number"
              value={runIdInput}
            />
            <button
              className="h-10 rounded-md border border-amber-200/20 px-4 text-sm font-semibold text-amber-100 transition hover:bg-amber-100/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70"
              type="submit"
            >
              적용
            </button>
            {hasFilters ? (
              <button
                className="h-10 rounded-md px-3 text-sm font-semibold text-slate-400 transition hover:bg-slate-800 hover:text-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70"
                onClick={handleClearFilters}
                type="button"
              >
                초기화
              </button>
            ) : null}
          </form>
        </div>
      </div>

      {isError ? (
        <div className="rounded-lg border border-rose-200/20 bg-rose-950/20 px-6 py-5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-rose-100">
                분석 목록을 불러오지 못했습니다.
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
      ) : analyses.length === 0 ? (
        <EmptyState hasFilters={hasFilters} onClear={handleClearFilters} />
      ) : (
        <div className="overflow-hidden rounded-lg border border-amber-100/10 bg-slate-950/45 shadow-2xl shadow-slate-950/30">
          <div className="hidden grid-cols-[9rem_1.1fr_0.55fr_0.8fr_6rem] gap-4 border-b border-amber-100/10 bg-slate-950/80 px-5 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 xl:grid">
            <span>created</span>
            <span>ticker / name</span>
            <span>judgment</span>
            <span>model</span>
            <span className="text-right">action</span>
          </div>
          <div className="divide-y divide-amber-100/10">
            {analyses.map((analysis) => (
              <AnalysisRow
                analysis={analysis}
                key={analysis.id}
                onSelect={() => navigate(`/analyses/${analysis.id}`)}
              />
            ))}
          </div>
        </div>
      )}

      <Link
        className="w-fit text-sm font-semibold text-slate-400 transition hover:text-amber-100"
        to="/runs"
      >
        실행 목록으로 이동
      </Link>
    </section>
  );
}

export default AnalysisListPage;
