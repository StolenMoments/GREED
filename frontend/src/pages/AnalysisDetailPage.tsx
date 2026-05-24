import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMemo, useState } from 'react';
import AnalysisBacktestPanel from '../components/AnalysisBacktestPanel';
import MarkdownRenderer from '../components/MarkdownRenderer';
import PriceLevels from '../components/PriceLevels';
import QuickAnalysisLauncher from '../components/QuickAnalysisLauncher';
import {
  getSignalTone,
  judgmentStyles,
  outcomeStyles,
  signalStyles,
} from '../constants/analysisStyles';
import {
  useAnalysis,
  useDeleteAnalysis,
  useEvaluateAnalysisOutcome,
  useHistory,
} from '../hooks/useAnalyses';
import { useRefreshStockPrice, useStockPrice } from '../hooks/useStockPrice';
import { formatDate, formatDateOnly } from '../utils/formatDate';
import { formatPriceByTicker } from '../utils/formatPrice';
import { parseMarkdown } from '../utils/parseMarkdown';
import type { Analysis, AnalysisSummary } from '../types';

function parseAnalysisId(idParam: string | undefined) {
  if (!idParam) {
    return undefined;
  }

  const parsed = Number(idParam);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function LoadingPanel() {
  return (
    <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="rounded-lg border border-amber-100/10 bg-slate-950/45 p-6">
        <div className="h-5 w-32 animate-pulse rounded bg-slate-800" />
        <div className="mt-4 h-9 w-80 max-w-full animate-pulse rounded bg-slate-800" />
        <div className="mt-6 grid grid-cols-5 gap-3">
          {Array.from({ length: 5 }, (_, index) => (
            <div
              className="h-16 animate-pulse rounded-md bg-slate-900"
              key={index}
            />
          ))}
        </div>
        <div className="mt-8 space-y-3">
          {Array.from({ length: 8 }, (_, index) => (
            <div
              className="h-4 animate-pulse rounded bg-slate-800"
              key={index}
              style={{ width: `${index % 3 === 0 ? 72 : 96}%` }}
            />
          ))}
        </div>
      </div>
      <div className="space-y-4">
        <div className="h-44 animate-pulse rounded-lg bg-slate-950/60" />
        <div className="h-72 animate-pulse rounded-lg bg-slate-950/60" />
      </div>
    </section>
  );
}

function ErrorPanel({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <section className="rounded-lg border border-rose-200/20 bg-rose-950/20 p-8">
      <p className="text-sm font-semibold text-rose-100">{message}</p>
      <div className="mt-5 flex gap-3">
        <Link
          className="rounded-md border border-amber-200/20 px-4 py-2 text-sm font-semibold text-amber-100 transition hover:bg-amber-100/10"
          to="/runs"
        >
          실행 목록으로
        </Link>
        {onRetry ? (
          <button
            className="rounded-md bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-amber-200"
            onClick={onRetry}
            type="button"
          >
            다시 시도
          </button>
        ) : null}
      </div>
    </section>
  );
}

function Metric({
  label,
  tone = 'neutral',
  value,
}: {
  label: string;
  tone?: keyof typeof signalStyles;
  value: string;
}) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/50 px-4 py-3">
      <dt className="text-xs font-medium text-slate-500">{label}</dt>
      <dd className={`mt-1 text-sm font-semibold ${signalStyles[tone]}`}>
        {value}
      </dd>
    </div>
  );
}

function CopyTickerButton({ ticker }: { ticker: string }) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>(
    'idle',
  );

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(ticker);
      setCopyState('copied');
    } catch {
      setCopyState('failed');
    }

    window.setTimeout(() => {
      setCopyState('idle');
    }, 1600);
  }

  const label =
    copyState === 'copied'
      ? '복사됨'
      : copyState === 'failed'
        ? '복사 실패'
        : '티커 복사';

  return (
    <button
      aria-label={`${ticker} 티커 클립보드 복사`}
      className={[
        'rounded-md border px-2.5 py-1 text-xs font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70',
        copyState === 'copied'
          ? 'border-emerald-300/40 bg-emerald-300/10 text-emerald-100'
          : copyState === 'failed'
            ? 'border-rose-300/40 bg-rose-300/10 text-rose-100'
            : 'border-amber-200/20 text-amber-100 hover:bg-amber-100/10',
      ].join(' ')}
      onClick={() => void handleCopy()}
      type="button"
    >
      {label}
    </button>
  );
}

function OutcomePanel({
  analysis,
  isEvaluating,
  isEvaluateError,
  onEvaluate,
}: {
  analysis: Analysis;
  isEvaluating: boolean;
  isEvaluateError: boolean;
  onEvaluate: () => void;
}) {
  const outcomePrice = formatPriceByTicker(
    analysis.outcome_price,
    analysis.ticker,
  );
  const canEvaluate = analysis.outcome === null || analysis.outcome === '진행중';

  return (
    <aside className="rounded-lg border border-amber-100/10 bg-slate-950/55 p-6">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-base font-semibold text-slate-100">판정 결과</h3>
        {analysis.outcome ? (
          <span
            className={[
              'rounded-full border px-3 py-1 text-xs font-semibold',
              outcomeStyles[analysis.outcome],
            ].join(' ')}
          >
            {analysis.outcome}
          </span>
        ) : (
          <span className="rounded-full border border-slate-800 bg-slate-900/60 px-3 py-1 text-xs font-semibold text-slate-600">
            미평가
          </span>
        )}
      </div>

      <dl className="mt-5 grid grid-cols-2 gap-3">
        <div className="rounded-md border border-slate-800 bg-slate-950/50 px-3 py-3">
          <dt className="text-xs font-medium text-slate-500">달성일</dt>
          <dd className="mt-1 whitespace-nowrap text-sm font-semibold text-slate-100">
            {analysis.outcome_date
              ? formatDateOnly(analysis.outcome_date)
              : '—'}
          </dd>
        </div>
        <div className="rounded-md border border-slate-800 bg-slate-950/50 px-3 py-3">
          <dt className="text-xs font-medium text-slate-500">달성가</dt>
          <dd className="mt-1 whitespace-nowrap text-sm font-semibold tabular-nums text-slate-100">
            {outcomePrice ?? '—'}
          </dd>
        </div>
      </dl>

      <p className="mt-4 text-xs leading-5 text-slate-500">
        일봉 고가/저가 기준으로 저장된 목표가 또는 손절가 도달 정보입니다.
      </p>

      <button
        className="mt-5 h-9 w-full rounded-md border border-amber-200/20 px-4 text-sm font-semibold text-amber-100 transition hover:bg-amber-100/10 disabled:cursor-not-allowed disabled:border-slate-800 disabled:text-slate-600 disabled:hover:bg-transparent focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70"
        disabled={!canEvaluate || isEvaluating}
        onClick={onEvaluate}
        type="button"
      >
        {isEvaluating ? '판정 중…' : '판정 실행'}
      </button>
      {isEvaluateError ? (
        <p className="mt-3 rounded-md border border-rose-300/20 bg-rose-950/20 px-3 py-2 text-xs leading-5 text-rose-100">
          판정을 실행하지 못했습니다.
        </p>
      ) : null}
    </aside>
  );
}

function HistoryList({
  activeId,
  history,
  isError,
  isLoading,
}: {
  activeId: number;
  history: AnalysisSummary[];
  isError: boolean;
  isLoading: boolean;
}) {
  const navigate = useNavigate();

  return (
    <aside className="rounded-lg border border-amber-100/10 bg-slate-950/55 p-4">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-100">분석 이력</h3>
        <span className="text-xs font-medium text-slate-500">
          {history.length}건
        </span>
      </div>

      {isLoading ? (
        <div className="mt-4 space-y-2">
          {Array.from({ length: 5 }, (_, index) => (
            <div
              className="h-16 animate-pulse rounded-md bg-slate-900"
              key={index}
            />
          ))}
        </div>
      ) : isError ? (
        <p className="mt-4 rounded-md border border-rose-300/20 bg-rose-950/20 px-3 py-2 text-xs leading-5 text-rose-100">
          이력을 불러오지 못했습니다.
        </p>
      ) : history.length === 0 ? (
        <p className="mt-4 text-sm leading-6 text-slate-400">
          같은 종목의 이전 분석이 없습니다.
        </p>
      ) : (
        <div className="mt-4 divide-y divide-amber-100/10">
          {history.map((item) => {
            const isActive = item.id === activeId;

            return (
              <button
                aria-current={isActive ? 'page' : undefined}
                aria-label={`${formatDate(item.created_at)} 분석 - 판정: ${item.judgment}`}
                className={[
                  'w-full px-3 py-3 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70',
                  isActive
                    ? 'rounded-md bg-amber-300/10'
                    : 'hover:bg-amber-100/[0.035]',
                ].join(' ')}
                key={item.id}
                onClick={() => {
                  if (!isActive) {
                    navigate(`/analyses/${item.id}`);
                  }
                }}
                type="button"
              >
                <span className="flex items-center justify-between gap-3">
                  <span className="text-sm font-semibold text-slate-100">
                    {formatDate(item.created_at)}
                  </span>
                  <span
                    className={[
                      'rounded-full border px-2 py-0.5 text-xs font-semibold',
                      judgmentStyles[item.judgment],
                    ].join(' ')}
                  >
                    {item.judgment}
                  </span>
                </span>
                <span className="mt-1 block text-xs text-slate-500">
                  run #{item.run_id} · {item.model}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </aside>
  );
}

function AnalysisDetailPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const analysisId = parseAnalysisId(id);
  const {
    data: analysis,
    isError,
    isLoading,
    refetch,
  } = useAnalysis(analysisId);
  const {
    data: history = [],
    isError: isHistoryError,
    isLoading: isHistoryLoading,
    refetch: refetchHistory,
  } = useHistory(analysisId);
  const { data: stockPrice } = useStockPrice(analysis?.ticker);
  const refreshStockPrice = useRefreshStockPrice(analysis?.ticker);
  const deleteAnalysisMutation = useDeleteAnalysis();
  const evaluateOutcomeMutation = useEvaluateAnalysisOutcome();
  const parsed = useMemo(
    () => (analysis ? parseMarkdown(analysis.markdown) : undefined),
    [analysis],
  );

  async function handleDeleteAnalysis() {
    if (!analysis) {
      return;
    }

    const confirmed = window.confirm(
      `Delete analysis #${analysis.id} (${analysis.ticker} ${analysis.name})?`,
    );

    if (!confirmed) {
      return;
    }

    try {
      await deleteAnalysisMutation.mutateAsync(analysis.id);
      navigate('/analyses');
    } catch {
      window.alert('Failed to delete analysis. Please try again.');
    }
  }

  if (!analysisId) {
    return <ErrorPanel message="분석 ID를 확인할 수 없습니다." />;
  }

  if (isLoading) {
    return <LoadingPanel />;
  }

  if (isError || !analysis || !parsed) {
    return (
      <ErrorPanel
        message="분석 상세를 불러오지 못했습니다."
        onRetry={() => void refetch()}
      />
    );
  }

  return (
    <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <article className="min-w-0 rounded-lg border border-amber-100/10 bg-slate-950/45 shadow-2xl shadow-slate-950/30">
        <div className="border-b border-amber-100/10 px-6 py-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-xs font-semibold uppercase tracking-[0.32em] text-amber-300">
                  {analysis.ticker}
                </p>
                <CopyTickerButton ticker={analysis.ticker} />
              </div>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-50">
                {analysis.name}
              </h2>
              <p className="mt-2 text-sm text-slate-500">
                run #{analysis.run_id} · {analysis.model} ·{' '}
                {formatDate(analysis.created_at)}
              </p>
            </div>

            <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
              <span
                className={[
                  'rounded-full border px-3 py-1.5 text-sm font-semibold',
                  judgmentStyles[analysis.judgment],
                ].join(' ')}
              >
                {analysis.judgment}
              </span>
              <button
                className="rounded-md border border-rose-300/25 px-3 py-2 text-sm font-semibold text-rose-100 transition hover:bg-rose-400/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-300/70 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={deleteAnalysisMutation.isPending}
                onClick={() => void handleDeleteAnalysis()}
                type="button"
              >
                삭제
              </button>
            </div>
          </div>

          <dl className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Metric
              label="추세"
              tone={getSignalTone(analysis.trend, '상승', '하락')}
              value={analysis.trend}
            />
            <Metric
              label="구름대"
              tone={getSignalTone(
                analysis.cloud_position,
                '구름 위',
                '구름 아래',
              )}
              value={analysis.cloud_position}
            />
            <Metric
              label="MA 배열"
              tone={getSignalTone(
                analysis.ma_alignment,
                '정배열',
                '역배열',
              )}
              value={analysis.ma_alignment}
            />
            <Metric label="분석 ID" value={`#${analysis.id}`} />
          </dl>
        </div>

        <div className="px-6 py-6">
          <MarkdownRenderer bodySize="base" markdown={analysis.markdown} />
        </div>
      </article>

      <div className="flex flex-col gap-4">
        <OutcomePanel
          analysis={analysis}
          isEvaluating={evaluateOutcomeMutation.isPending}
          isEvaluateError={evaluateOutcomeMutation.isError}
          onEvaluate={() => evaluateOutcomeMutation.mutate(analysis.id)}
        />
        <AnalysisBacktestPanel analysisId={analysis.id} />
        <PriceLevels
          ticker={analysis.ticker}
          currentPrice={stockPrice}
          entryPrice={analysis.entry_price ?? parsed.data.entry_price}
          entryPriceMax={analysis.entry_price_max ?? parsed.data.entry_price_max}
          isRefreshing={refreshStockPrice.isPending}
          onRefresh={() => refreshStockPrice.mutate()}
          refreshError={refreshStockPrice.isError}
          targetPrice={analysis.target_price ?? parsed.data.target_price}
          targetPriceMax={analysis.target_price_max ?? parsed.data.target_price_max}
          stopLoss={analysis.stop_loss ?? parsed.data.stop_loss}
          stopLossMax={analysis.stop_loss_max ?? parsed.data.stop_loss_max}
        />
        <QuickAnalysisLauncher
          defaultModel={analysis.model}
          onAnalysisCreated={() => void refetchHistory()}
          runId={analysis.run_id}
          ticker={analysis.ticker}
        />
        <HistoryList
          activeId={analysis.id}
          history={history}
          isError={isHistoryError}
          isLoading={isHistoryLoading}
        />
      </div>
    </section>
  );
}

export default AnalysisDetailPage;
