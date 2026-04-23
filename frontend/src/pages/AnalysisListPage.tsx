import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { FormEvent, useEffect, useMemo, useState } from 'react';
import { AnalysisTable, AnalysisTableLoading } from '../components/AnalysisTable';
import { useAllAnalyses } from '../hooks/useAnalyses';
import type { AnalysisFilters, EntryCandidateFilter, Judgment } from '../types';

const DEFAULT_PAGE_SIZE = 25;
const ENTRY_GAP_FILTER_PCT = 2;

const judgmentTabs: Array<{ label: string; value?: Judgment }> = [
  { label: '전체' },
  { label: '매수', value: '매수' },
  { label: '홀드', value: '홀드' },
  { label: '매도', value: '매도' },
];

const entryCandidateTabs: Array<{
  label: string;
  value: EntryCandidateFilter;
}> = [
  { label: '전체 2%', value: 'all' },
  { label: '눌림 2%', value: 'pullback' },
  { label: '돌파 2%', value: 'breakout' },
];

interface PaginationControlsProps {
  disabled: boolean;
  onPageChange: (page: number) => void;
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

function isValidJudgment(value: string | null): value is Judgment {
  return judgmentTabs.some((tab) => tab.value === value);
}

function isValidEntryCandidate(
  value: string | null,
): value is EntryCandidateFilter {
  return entryCandidateTabs.some((tab) => tab.value === value);
}

function parseRunId(value: string | null) {
  if (!value) {
    return undefined;
  }

  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function parsePage(value: string | null) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : 1;
}

function parsePageSize(value: string | null) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 && parsed <= 100
    ? parsed
    : DEFAULT_PAGE_SIZE;
}

function parseEntryGapLte(value: string | null) {
  if (!value) {
    return undefined;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
}

function getVisiblePages(page: number, totalPages: number) {
  const end = Math.min(totalPages, Math.max(page + 2, 5));
  const start = Math.max(1, Math.min(page - 2, end - 4));

  return Array.from({ length: end - start + 1 }, (_, index) => start + index);
}

function EmptyState({
  entryCandidateFilter,
  hasFilters,
  hasSearch,
  onClear,
}: {
  entryCandidateFilter?: EntryCandidateFilter;
  hasFilters: boolean;
  hasSearch: boolean;
  onClear: () => void;
}) {
  const entryCandidateEmptyMessages: Record<EntryCandidateFilter, string> = {
    all: '진입 2% 이내 후보가 없습니다.',
    pullback: '눌림 2% 이내 후보가 없습니다.',
    breakout: '돌파 2% 이내 후보가 없습니다.',
  };

  return (
    <div className="rounded-lg border border-amber-100/10 bg-slate-950/45 px-6 py-12 text-center">
      <p className="text-sm font-semibold text-slate-100">
        {hasSearch
          ? '검색 조건에 맞는 분석이 없습니다.'
          : entryCandidateFilter
            ? entryCandidateEmptyMessages[entryCandidateFilter]
            : '조건에 맞는 분석이 없습니다.'}
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

function PaginationControls({
  disabled,
  onPageChange,
  page,
  pageSize,
  total,
  totalPages,
}: PaginationControlsProps) {
  const firstItem = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const lastItem = Math.min(page * pageSize, total);
  const pages = getVisiblePages(page, totalPages);
  const isFirstPage = page <= 1;
  const isLastPage = totalPages === 0 || page >= totalPages;
  const buttonBase =
    'h-9 rounded-md border px-3 text-sm font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70 disabled:cursor-not-allowed disabled:border-slate-800 disabled:text-slate-700 disabled:hover:bg-transparent';

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-amber-100/10 pt-4">
      <p className="text-sm font-medium text-slate-400">
        <span className="text-slate-200">
          {firstItem.toLocaleString('ko-KR')}-{lastItem.toLocaleString('ko-KR')}
        </span>{' '}
        / 총 {total.toLocaleString('ko-KR')}개
      </p>

      {totalPages > 1 ? (
        <nav
          aria-label="전체 분석 목록 페이지"
          className="flex flex-wrap items-center gap-1.5"
        >
          <button
            className={`${buttonBase} border-slate-700/80 text-slate-300 hover:bg-slate-800 hover:text-slate-50`}
            disabled={disabled || isFirstPage}
            onClick={() => onPageChange(1)}
            type="button"
          >
            처음
          </button>
          <button
            className={`${buttonBase} border-slate-700/80 text-slate-300 hover:bg-slate-800 hover:text-slate-50`}
            disabled={disabled || isFirstPage}
            onClick={() => onPageChange(page - 1)}
            type="button"
          >
            이전
          </button>

          {pages.map((pageNumber) => {
            const isActive = pageNumber === page;

            return (
              <button
                aria-current={isActive ? 'page' : undefined}
                className={[
                  buttonBase,
                  isActive
                    ? 'border-amber-300 bg-amber-300 text-slate-950'
                    : 'border-slate-700/80 text-slate-300 hover:bg-slate-800 hover:text-slate-50',
                ].join(' ')}
                disabled={disabled || isActive}
                key={pageNumber}
                onClick={() => onPageChange(pageNumber)}
                type="button"
              >
                {pageNumber}
              </button>
            );
          })}

          <button
            className={`${buttonBase} border-slate-700/80 text-slate-300 hover:bg-slate-800 hover:text-slate-50`}
            disabled={disabled || isLastPage}
            onClick={() => onPageChange(page + 1)}
            type="button"
          >
            다음
          </button>
          <button
            className={`${buttonBase} border-slate-700/80 text-slate-300 hover:bg-slate-800 hover:text-slate-50`}
            disabled={disabled || isLastPage}
            onClick={() => onPageChange(totalPages)}
            type="button"
          >
            끝
          </button>
        </nav>
      ) : null}
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
  const activePage = parsePage(searchParams.get('page'));
  const activePageSize = parsePageSize(searchParams.get('page_size'));
  const activeEntryGapLte = parseEntryGapLte(searchParams.get('entry_gap_lte'));
  const isEntryGapFilterActive = activeEntryGapLte === ENTRY_GAP_FILTER_PCT;
  const requestedEntryCandidate = searchParams.get('entry_candidate');
  const activeEntryCandidate = isEntryGapFilterActive
    ? isValidEntryCandidate(requestedEntryCandidate)
      ? requestedEntryCandidate
      : 'all'
    : undefined;
  const [queryInput, setQueryInput] = useState(activeQuery);
  const [runIdInput, setRunIdInput] = useState(
    activeRunId ? String(activeRunId) : '',
  );
  const filters = useMemo<AnalysisFilters>(
    () => ({
      ...(activeJudgment ? { judgment: activeJudgment } : {}),
      ...(activeRunId ? { run_id: activeRunId } : {}),
      ...(activeQuery ? { q: activeQuery } : {}),
      ...(activeEntryGapLte !== undefined ? { entry_gap_lte: activeEntryGapLte } : {}),
      ...(activeEntryCandidate ? { entry_candidate: activeEntryCandidate } : {}),
    }),
    [
      activeEntryCandidate,
      activeEntryGapLte,
      activeJudgment,
      activeQuery,
      activeRunId,
    ],
  );
  const {
    data: analysisPage,
    isError,
    isFetching,
    isLoading,
    refetch,
  } = useAllAnalyses(filters, {
    page: activePage,
    page_size: activePageSize,
  });
  const analyses = analysisPage?.items ?? [];
  const hasFilters = Boolean(
    activeJudgment || activeRunId || activeQuery || activeEntryGapLte !== undefined,
  );
  const showInitialLoading = isLoading && !analysisPage;

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
          ...(activeEntryGapLte !== undefined ? { entry_gap_lte: activeEntryGapLte } : {}),
          ...(activeEntryCandidate ? { entry_candidate: activeEntryCandidate } : {}),
        },
        true,
      );
    }, 300);

    return () => window.clearTimeout(timeoutId);
  }, [
    activeEntryCandidate,
    activeEntryGapLte,
    activeJudgment,
    activeQuery,
    activeRunId,
    queryInput,
  ]);

  useEffect(() => {
    if (
      analysisPage &&
      analysisPage.total_pages > 0 &&
      activePage > analysisPage.total_pages
    ) {
      updateFilters(filters, true, analysisPage.total_pages);
    }
  }, [activePage, analysisPage, filters]);

  function updateFilters(
    next: AnalysisFilters,
    replace = false,
    nextPage = 1,
  ) {
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

    if (next.entry_gap_lte !== undefined) {
      params.set('entry_gap_lte', String(next.entry_gap_lte));
      params.set('entry_candidate', next.entry_candidate ?? 'all');
    }

    params.set('page', String(nextPage));
    params.set('page_size', String(activePageSize));

    setSearchParams(params, replace ? { replace: true } : undefined);
  }

  function handleJudgmentChange(judgment?: Judgment) {
    updateFilters({
      ...(judgment ? { judgment } : {}),
      ...(activeRunId ? { run_id: activeRunId } : {}),
      ...(activeQuery ? { q: activeQuery } : {}),
      ...(activeEntryGapLte !== undefined ? { entry_gap_lte: activeEntryGapLte } : {}),
      ...(activeEntryCandidate ? { entry_candidate: activeEntryCandidate } : {}),
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
      ...(activeEntryGapLte !== undefined ? { entry_gap_lte: activeEntryGapLte } : {}),
      ...(activeEntryCandidate ? { entry_candidate: activeEntryCandidate } : {}),
    });
  }

  function handleEntryGapFilterChange(entryCandidate: EntryCandidateFilter) {
    const shouldClear =
      isEntryGapFilterActive && activeEntryCandidate === entryCandidate;

    updateFilters({
      ...(activeJudgment ? { judgment: activeJudgment } : {}),
      ...(activeRunId ? { run_id: activeRunId } : {}),
      ...(activeQuery ? { q: activeQuery } : {}),
      ...(!shouldClear
        ? {
            entry_candidate: entryCandidate,
            entry_gap_lte: ENTRY_GAP_FILTER_PCT,
          }
        : {}),
    });
  }

  function handleClearFilters() {
    setQueryInput('');
    setRunIdInput('');
    setSearchParams({
      page: '1',
      page_size: String(DEFAULT_PAGE_SIZE),
    });
  }

  function handlePageChange(nextPage: number) {
    updateFilters(filters, false, nextPage);
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
                placeholder="종목명, 초성 또는 티커"
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
            <div
              aria-label="진입 후보 2% 이내 필터"
              className="flex h-10 items-center rounded-lg border border-amber-100/10 bg-slate-950/70 p-1"
            >
              {entryCandidateTabs.map((tab) => {
                const isActive = activeEntryCandidate === tab.value;

                return (
                  <button
                    aria-pressed={isActive}
                    className={[
                      'h-8 rounded-md px-3 text-sm font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70',
                      isActive
                        ? 'bg-amber-300 text-slate-950'
                        : 'text-amber-100 hover:bg-amber-100/10',
                    ].join(' ')}
                    key={tab.value}
                    onClick={() => handleEntryGapFilterChange(tab.value)}
                    type="button"
                  >
                    {tab.label}
                  </button>
                );
              })}
            </div>
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
      ) : showInitialLoading ? (
        <AnalysisTableLoading showEntryGap />
      ) : analyses.length === 0 ? (
        <EmptyState
          hasFilters={hasFilters}
          hasSearch={Boolean(activeQuery)}
          entryCandidateFilter={activeEntryCandidate}
          onClear={handleClearFilters}
        />
      ) : (
        <div
          className={[
            'flex flex-col gap-4 transition-opacity',
            isFetching ? 'opacity-70' : 'opacity-100',
          ].join(' ')}
        >
          <AnalysisTable
            analyses={analyses}
            entryCandidateFilter={activeEntryCandidate ?? 'all'}
            onSelect={(analysis) => navigate(`/analyses/${analysis.id}`)}
            showEntryGap
            showRunId
          />
          <PaginationControls
            disabled={isFetching}
            onPageChange={handlePageChange}
            page={analysisPage?.page ?? activePage}
            pageSize={analysisPage?.page_size ?? activePageSize}
            total={analysisPage?.total ?? 0}
            totalPages={analysisPage?.total_pages ?? 0}
          />
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
