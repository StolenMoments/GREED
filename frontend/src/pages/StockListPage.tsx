import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMemo, useState } from 'react';
import ManualInputModal from '../components/ManualInputModal';
import { getSignalTone, judgmentStyles, signalStyles } from '../constants/analysisStyles';
import { useAnalyses } from '../hooks/useAnalyses';
import type {
  Analysis,
  AnalysisFilters,
  AnalysisSummary,
  Judgment,
} from '../types';

const judgmentTabs: Array<{ label: string; value?: Judgment }> = [
  { label: '전체' },
  { label: '매수', value: '매수' },
  { label: '홀드', value: '홀드' },
  { label: '매도', value: '매도' },
];

function parseRunId(runIdParam: string | undefined) {
  if (!runIdParam) {
    return undefined;
  }

  const parsed = Number(runIdParam);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function isValidJudgment(value: string | null): value is Judgment {
  return judgmentTabs.some((tab) => tab.value === value);
}

function LoadingRows() {
  return (
    <div className="divide-y divide-amber-100/10 rounded-lg border border-amber-100/10 bg-slate-950/45">
      {Array.from({ length: 6 }, (_, index) => (
        <div
          className="grid grid-cols-[minmax(14rem,1.35fr)_7rem_0.75fr_0.75fr_0.75fr] items-center gap-4 px-5 py-4"
          key={index}
        >
          <div className="space-y-2">
            <div className="h-4 w-24 animate-pulse rounded bg-slate-700/60" />
            <div className="h-3 w-36 animate-pulse rounded bg-slate-800/80" />
          </div>
          <div className="h-8 w-16 animate-pulse rounded-full bg-slate-800/80" />
          <div className="h-4 w-16 animate-pulse rounded bg-slate-800/80" />
          <div className="h-4 w-20 animate-pulse rounded bg-slate-800/80" />
          <div className="h-4 w-16 animate-pulse rounded bg-slate-800/80" />
        </div>
      ))}
    </div>
  );
}

function EmptyState({ activeLabel }: { activeLabel: string }) {
  return (
    <div className="rounded-lg border border-amber-100/10 bg-slate-950/45 px-6 py-12 text-center">
      <p className="text-sm font-semibold text-slate-100">
        {activeLabel} 조건에 맞는 분석이 없습니다.
      </p>
      <p className="mt-2 text-sm text-slate-400">
        다른 판정 탭을 선택해 이 실행의 종목을 다시 확인하세요.
      </p>
    </div>
  );
}

function StockRow({ analysis }: { analysis: AnalysisSummary }) {
  const navigate = useNavigate();

  return (
    <button
      aria-label={`${analysis.name} (${analysis.ticker}) 분석 상세 보기`}
      className="grid w-full grid-cols-[minmax(14rem,1.35fr)_7rem_0.75fr_0.75fr_0.75fr] items-center gap-4 px-5 py-4 text-left transition hover:bg-amber-100/[0.035] focus:outline-none focus-visible:bg-amber-100/[0.05] focus-visible:ring-2 focus-visible:ring-amber-300/70"
      onClick={() => navigate(`/analyses/${analysis.id}`)}
      type="button"
    >
      <span className="min-w-0">
        <span className="block truncate text-lg font-semibold text-slate-50">
          {analysis.name}
        </span>
        <span className="mt-1 block text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
          {analysis.ticker}
        </span>
      </span>

      <span
        className={[
          'inline-flex min-w-16 justify-center rounded-full border px-3.5 py-1.5 text-sm font-semibold',
          judgmentStyles[analysis.judgment],
        ].join(' ')}
      >
        {analysis.judgment}
      </span>

      <span className={`text-sm font-medium ${signalStyles[getSignalTone(analysis.trend, '상승', '하락')]}`}>
        {analysis.trend}
      </span>
      <span className={`text-sm font-medium ${signalStyles[getSignalTone(analysis.cloud_position, '구름 위', '구름 아래')]}`}>
        {analysis.cloud_position}
      </span>
      <span className={`text-sm font-medium ${signalStyles[getSignalTone(analysis.ma_alignment, '정배열', '역배열')]}`}>
        {analysis.ma_alignment}
      </span>
    </button>
  );
}

function StockListPage() {
  const navigate = useNavigate();
  const { runId: runIdParam } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [isManualModalOpen, setIsManualModalOpen] = useState(false);
  const runId = parseRunId(runIdParam);
  const requestedJudgment = searchParams.get('judgment');
  const activeJudgment = isValidJudgment(requestedJudgment)
    ? requestedJudgment
    : undefined;
  const filters = useMemo<AnalysisFilters>(
    () => (activeJudgment ? { judgment: activeJudgment } : {}),
    [activeJudgment],
  );
  const { data: analyses = [], isError, isLoading, refetch } = useAnalyses(
    runId,
    filters,
  );

  const activeLabel =
    judgmentTabs.find((tab) => tab.value === activeJudgment)?.label ?? '전체';

  function handleManualSaved(analysis: Analysis) {
    if (analysis.run_id !== runId) {
      navigate(`/runs/${analysis.run_id}`);
      return;
    }

    void refetch();
  }

  if (!runId) {
    return (
      <section className="rounded-lg border border-rose-200/20 bg-rose-950/20 p-8">
        <p className="text-sm font-semibold text-rose-100">
          실행 ID를 확인할 수 없습니다.
        </p>
        <Link
          className="mt-4 inline-flex rounded-md border border-amber-200/20 px-4 py-2 text-sm font-semibold text-amber-100 transition hover:bg-amber-100/10"
          to="/runs"
        >
          실행 목록으로 돌아가기
        </Link>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex items-end justify-between gap-6 border-b border-amber-100/10 pb-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.32em] text-amber-300">
            run #{runId}
          </p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-50">
            종목 분석 목록
          </h2>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-3">
          <button
            className="rounded-md bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-amber-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70"
            onClick={() => setIsManualModalOpen(true)}
            type="button"
          >
            수동 입력
          </button>

          <div
            className="flex items-center rounded-lg border border-amber-100/10 bg-slate-950/70 p-1"
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
                  onClick={() => {
                    if (tab.value) {
                      setSearchParams({ judgment: tab.value });
                    } else {
                      setSearchParams({});
                    }
                  }}
                  role="tab"
                  type="button"
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {isError ? (
        <div className="rounded-lg border border-rose-200/20 bg-rose-950/20 px-6 py-5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-rose-100">
                종목 목록을 불러오지 못했습니다.
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
        <EmptyState activeLabel={activeLabel} />
      ) : (
        <div className="overflow-hidden rounded-lg border border-amber-100/10 bg-slate-950/45 shadow-2xl shadow-slate-950/30">
          <div className="grid grid-cols-[minmax(14rem,1.35fr)_7rem_0.75fr_0.75fr_0.75fr] gap-4 border-b border-amber-100/10 bg-slate-950/80 px-5 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
            <span>ticker / name</span>
            <span>judgment</span>
            <span>trend</span>
            <span>cloud</span>
            <span>ma</span>
          </div>
          <div className="divide-y divide-amber-100/10">
            {analyses.map((analysis) => (
              <StockRow analysis={analysis} key={analysis.id} />
            ))}
          </div>
        </div>
      )}

      <ManualInputModal
        defaultRunId={runId}
        isOpen={isManualModalOpen}
        onClose={() => setIsManualModalOpen(false)}
        onSaved={handleManualSaved}
      />
    </section>
  );
}

export default StockListPage;
