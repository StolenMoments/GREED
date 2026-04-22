import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { FormEvent, useEffect, useMemo, useState } from 'react';
import { AnalysisTable, AnalysisTableLoading } from '../components/AnalysisTable';
import { useAllAnalyses } from '../hooks/useAnalyses';
import type { AnalysisFilters, Judgment } from '../types';

const judgmentTabs: Array<{ label: string; value?: Judgment }> = [
  { label: '전체' },
  { label: '매수', value: '매수' },
  { label: '홀드', value: '홀드' },
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

function EmptyState({
  hasFilters,
  hasSearch,
  onClear,
}: {
  hasFilters: boolean;
  hasSearch: boolean;
  onClear: () => void;
}) {
  return (
    <div className="rounded-lg border border-amber-100/10 bg-slate-950/45 px-6 py-12 text-center">
      <p className="text-sm font-semibold text-slate-100">
        {hasSearch ? '검색 조건에 맞는 분석이 없습니다.' : '조건에 맞는 분석이 없습니다.'}
      </p>
      <p className="mt-2 text-sm text-slate-400">
        {hasFilters
          ? '필터를 조정해 다른 분석을 확인하세요.'
          : '분석이 저장되면 최신 항목부터 여기에 표시됩니다.'}
      </p>
      <button
        className="mt-6 rounded-md border border-amber-200/20 px-4 py-2 text-sm font-semibold text-amber-100 transition hover:bg-amber-100/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70 disabled:cursor-not-allowed disabled:border-slate-700/60 disabled:text-slate-600 disabled:hover:bg-transparent"
        disabled={!hasFilters}
        onClick={onClear}
        type="button"
      >
        필터 초기화
      </button>
    </div>
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
  const activeQuery = (searchParams.get('q') ?? '').trim();
  const [queryInput, setQueryInput] = useState(activeQuery);
  const [runIdInput, setRunIdInput] = useState(
    activeRunId ? String(activeRunId) : '',
  );
  const filters = useMemo<AnalysisFilters>(
    () => ({
      ...(activeJudgment ? { judgment: activeJudgment } : {}),
      ...(activeRunId ? { run_id: activeRunId } : {}),
      ...(activeQuery ? { q: activeQuery } : {}),
    }),
    [activeJudgment, activeQuery, activeRunId],
  );
  const {
    data: analyses = [],
    isError,
    isLoading,
    refetch,
  } = useAllAnalyses(filters);
  const hasFilters = Boolean(activeJudgment || activeRunId || activeQuery);

  useEffect(() => {
    setRunIdInput(activeRunId ? String(activeRunId) : '');
  }, [activeRunId]);

  useEffect(() => {
    setQueryInput(activeQuery);
  }, [activeQuery]);

  useEffect(() => {
    const nextQuery = queryInput.trim();

    if (nextQuery === activeQuery) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      updateFilters(
        {
          ...(activeJudgment ? { judgment: activeJudgment } : {}),
          ...(activeRunId ? { run_id: activeRunId } : {}),
          ...(nextQuery ? { q: nextQuery } : {}),
        },
        true,
      );
    }, 300);

    return () => window.clearTimeout(timeoutId);
  }, [activeJudgment, activeQuery, activeRunId, queryInput]);

  function updateFilters(next: AnalysisFilters, replace = false) {
    const params = new URLSearchParams();

    if (next.judgment) {
      params.set('judgment', next.judgment);
    }

    if (next.run_id) {
      params.set('run_id', String(next.run_id));
    }

    if (next.q) {
      params.set('q', next.q);
    }

    setSearchParams(params, replace ? { replace: true } : undefined);
  }

  function handleJudgmentChange(judgment?: Judgment) {
    updateFilters({
      ...(judgment ? { judgment } : {}),
      ...(activeRunId ? { run_id: activeRunId } : {}),
      ...(activeQuery ? { q: activeQuery } : {}),
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
      ...(activeQuery ? { q: activeQuery } : {}),
    });
  }

  function handleClearFilters() {
    setQueryInput('');
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
            className="flex flex-wrap items-end justify-end gap-2"
            onSubmit={handleRunFilterSubmit}
          >
            <label
              className="flex min-w-64 flex-col gap-1.5 text-sm font-medium text-slate-400"
              htmlFor="analysis-query-filter"
            >
              종목 검색
              <input
                className="h-10 rounded-md border border-slate-700/80 bg-slate-950/70 px-3 text-sm font-medium text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-amber-300/50 focus:ring-2 focus:ring-amber-300/20"
                id="analysis-query-filter"
                onChange={(event) => setQueryInput(event.target.value)}
                placeholder="종목명 또는 티커"
                type="search"
                value={queryInput}
              />
            </label>
            <label
              className="flex flex-col gap-1.5 text-sm font-medium text-slate-400"
              htmlFor="run-id-filter"
            >
              실행 ID
              <input
                className="h-10 w-28 rounded-md border border-slate-700/80 bg-slate-950/70 px-3 text-sm font-medium text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-amber-300/50 focus:ring-2 focus:ring-amber-300/20"
                id="run-id-filter"
                min={1}
                onChange={(event) => setRunIdInput(event.target.value)}
                placeholder="예: 12"
                type="number"
                value={runIdInput}
              />
            </label>
            <button
              className="h-10 rounded-md border border-amber-200/20 px-4 text-sm font-semibold text-amber-100 transition hover:bg-amber-100/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70"
              type="submit"
            >
              적용
            </button>
            <button
              className="h-10 rounded-md px-3 text-sm font-semibold text-slate-400 transition hover:bg-slate-800 hover:text-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70 disabled:cursor-not-allowed disabled:text-slate-700 disabled:hover:bg-transparent disabled:hover:text-slate-700"
              disabled={!hasFilters}
              onClick={handleClearFilters}
              type="button"
            >
              초기화
            </button>
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
        <AnalysisTableLoading />
      ) : analyses.length === 0 ? (
        <EmptyState
          hasFilters={hasFilters}
          hasSearch={Boolean(activeQuery)}
          onClear={handleClearFilters}
        />
      ) : (
        <AnalysisTable
          analyses={analyses}
          onSelect={(analysis) => navigate(`/analyses/${analysis.id}`)}
          showRunId
        />
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
