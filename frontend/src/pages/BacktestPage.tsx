import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import {
  fetchBacktestRun,
  fetchBacktestRuns,
  type BacktestRunSummary,
  type BacktestRunDetail,
  type BacktestStat,
  type BacktestEventSummary,
} from '../api/backtest';
import { bucketHorizonKey, rankTopWinRateCells } from './backtestHighlights';

const HORIZONS = [4, 8, 12, 26] as const;
const LEGACY_BUCKETS = ['4-5', '6-7', '8+'] as const;
const SIMILARITY_BUCKETS = ['10', '11', '12', '13', '14'] as const;

function ratio(value: number | null, digits = 1): string {
  if (value === null) return '--';
  return `${(value * 100).toFixed(digits)}%`;
}

function pct(value: number | null, digits = 1): string {
  if (value === null) return '--';
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(digits)}%`;
}

function count(value: number | undefined): string {
  return (value ?? 0).toLocaleString('ko-KR');
}

function date(value: string | null): string {
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
      className={`${className} animate-pulse rounded-xl border border-amber-100/10 bg-slate-950/60`}
    />
  );
}

function ErrorPanel({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-lg border border-rose-200/20 bg-rose-950/20 px-6 py-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-rose-100">
            백테스트 결과를 불러오지 못했습니다.
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

function EmptyState() {
  return (
    <div className="rounded-lg border border-amber-100/10 bg-slate-950/45 px-6 py-12 text-center">
      <p className="text-sm font-semibold text-slate-100">
        아직 백테스트 실행 결과가 없습니다.
      </p>
      <p className="mt-2 text-sm text-slate-400">
        `python -m scripts.backtest.run`으로 결과를 생성한 뒤 다시 확인하세요.
      </p>
    </div>
  );
}

function RunSelector({
  detail,
  runId,
  runs,
  onChange,
}: {
  detail: BacktestRunDetail | undefined;
  runId: number | null;
  runs: BacktestRunSummary[];
  onChange: (id: number) => void;
}) {
  const isSimilarity = detail?.strategy_kind === 'analysis_similarity';
  const isContract = detail?.strategy_kind === 'analysis_contract';

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-6">
        <div className="flex items-center gap-3">
          <span className="text-sm text-slate-400">실행 선택</span>
          <select
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 transition focus:outline-none focus:ring-1 focus:ring-amber-400/60"
            value={runId ?? ''}
            onChange={(event) => onChange(Number(event.target.value))}
          >
            {runs.map((run) => (
              <option key={run.id} value={run.id}>
                {run.source_name
                  ? `#${run.id} · ${run.source_name} · ${date(run.created_at)} · 신호 ${run.signal_count.toLocaleString('ko-KR')}`
                  : `#${run.id} · ${date(run.created_at)} · 신호 ${run.signal_count.toLocaleString('ko-KR')}`}
              </option>
            ))}
          </select>
        </div>

        {detail && (isSimilarity || isContract) && detail.source_name && (
          <div className="flex items-baseline gap-3">
            <span className="text-3xl font-semibold tracking-tight text-amber-200">
              {detail.source_name}
            </span>
            {detail.source_ticker && (
              <span className="text-lg text-slate-400">{detail.source_ticker}</span>
            )}
            {detail.source_analysis_id !== null && (
              <Link
                className="rounded border border-amber-200/25 px-2.5 py-1 text-lg font-semibold text-amber-300/80 transition hover:border-amber-300/50 hover:text-amber-200"
                to={`/analyses/${detail.source_analysis_id}`}
              >
                분석 #{detail.source_analysis_id}
              </Link>
            )}
          </div>
        )}
      </div>

      {detail && (
        <div className="text-xs text-slate-500">
          <span>
            {detail.universe} · 종목 {detail.ticker_count.toLocaleString('ko-KR')}개 ·
            기준점 {detail.buy_threshold}
            {isSimilarity ? ` · similarity ${detail.similarity_threshold ?? '--'}` : null}
            {isContract ? ` · contract similarity ${detail.similarity_threshold ?? '--'}` : null}
            {' · '}{date(detail.data_start)} ~ {date(detail.data_end)} · 워밍업 {detail.warmup_weeks}주
          </span>
        </div>
      )}
    </div>
  );
}

function SummaryStrip({ detail }: { detail: BacktestRunDetail }) {
  if (detail.strategy_kind === 'analysis_contract' && detail.event_summary) {
    const summary = detail.event_summary;
    return (
      <div className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-slate-800/80 bg-slate-950/60 px-5 py-4">
          <p className="text-xs text-slate-500">contract signals</p>
          <p className="mt-1 text-2xl font-semibold text-slate-50">
            {summary.signal_count.toLocaleString('ko-KR')}
          </p>
        </div>
        <div className="rounded-lg border border-slate-800/80 bg-slate-950/60 px-5 py-4">
          <p className="text-xs text-slate-500">entered / missed</p>
          <p className="mt-1 text-2xl font-semibold text-slate-50">
            {summary.entered_count.toLocaleString('ko-KR')}
            <span className="text-base font-medium text-slate-500">
              {' / '}{summary.no_entry_count.toLocaleString('ko-KR')}
            </span>
          </p>
        </div>
        <div className="rounded-lg border border-slate-800/80 bg-slate-950/60 px-5 py-4">
          <p className="text-xs text-slate-500">target win rate</p>
          <p className="mt-1 text-2xl font-semibold text-emerald-300">
            {ratio(summary.win_rate)}
          </p>
        </div>
        <div className="rounded-lg border border-slate-800/80 bg-slate-950/60 px-5 py-4">
          <p className="text-xs text-slate-500">mean event return</p>
          <p className={`mt-1 text-2xl font-semibold ${signedTone(summary.mean_return)}`}>
            {pct(summary.mean_return)}
          </p>
        </div>
      </div>
    );
  }

  const allStats = detail.stats.filter((stat) => stat.score_bucket === 'ALL');
  const namedH4 = detail.stats.filter(
    (stat) => stat.horizon === 4 && stat.score_bucket !== 'ALL' && stat.score_bucket !== '8-9',
  );
  const signalCount = namedH4.length > 0
    ? namedH4.reduce((sum, stat) => sum + stat.count, 0)
    : Math.max(...allStats.map((stat) => stat.count), detail.signal_count, 0);
  const bestMean = allStats.reduce<BacktestStat | undefined>((best, stat) => {
    if (stat.mean === null) return best;
    if (!best || best.mean === null || stat.mean > best.mean) return stat;
    return best;
  }, undefined);

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <div className="rounded-lg border border-slate-800/80 bg-slate-950/60 px-5 py-4">
        <p className="text-xs text-slate-500">전체 신호</p>
        <p className="mt-1 text-2xl font-semibold text-slate-50">
          {signalCount.toLocaleString('ko-KR')}
        </p>
      </div>
      <div className="rounded-lg border border-slate-800/80 bg-slate-950/60 px-5 py-4">
        <p className="text-xs text-slate-500">최고 평균 수익률</p>
        <p className={`mt-1 text-2xl font-semibold ${signedTone(bestMean?.mean)}`}>
          {pct(bestMean?.mean ?? null)}
        </p>
        <p className="mt-1 text-xs text-slate-500">
          {bestMean ? `${bestMean.horizon}주 보유` : '--'}
        </p>
      </div>
      <div className="rounded-lg border border-slate-800/80 bg-slate-950/60 px-5 py-4">
        <p className="text-xs text-slate-500">수익률 구간</p>
        <p className="mt-1 text-2xl font-semibold text-slate-50">
          {detail.horizons.replaceAll(',', ' / ')}주
        </p>
      </div>
    </div>
  );
}

function ContractEventSummaryPanel({ summary }: { summary: BacktestEventSummary }) {
  const outcomes = [
    { label: 'Target', value: summary.target_count, tone: 'text-emerald-200' },
    { label: 'Stop', value: summary.stop_count, tone: 'text-rose-200' },
    { label: 'Expiry', value: summary.expiry_count, tone: 'text-amber-100' },
    { label: 'No entry', value: summary.no_entry_count, tone: 'text-slate-400' },
  ];
  const max = Math.max(...outcomes.map((item) => item.value), 1);

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(280px,0.6fr)]">
      <div className="rounded-lg border border-slate-800/80 bg-slate-950/55 p-5">
        <div className="border-b border-amber-100/10 pb-3">
          <p className="text-xs font-semibold uppercase tracking-[0.32em] text-amber-300">
            contract outcomes
          </p>
          <h3 className="mt-2 text-xl font-semibold tracking-tight text-slate-50">
            Entry touch to target / stop / expiry
          </h3>
        </div>
        <div className="mt-5 grid gap-3">
          {outcomes.map((item) => (
            <div className="grid grid-cols-[92px_minmax(0,1fr)_72px] items-center gap-3" key={item.label}>
              <span className={`text-sm font-semibold ${item.tone}`}>{item.label}</span>
              <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                <div
                  className="h-full rounded-full bg-amber-300"
                  style={{ width: `${(item.value / max) * 100}%` }}
                />
              </div>
              <span className="text-right text-sm font-semibold text-slate-200">
                {item.value.toLocaleString('ko-KR')}
              </span>
            </div>
          ))}
        </div>
      </div>
      <div className="rounded-lg border border-slate-800/80 bg-slate-950/55 p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.32em] text-amber-300">
          holding
        </p>
        <p className="mt-4 text-3xl font-semibold text-slate-50">
          {summary.avg_days_held === null ? '--' : summary.avg_days_held.toFixed(1)}
          <span className="ml-2 text-base font-medium text-slate-500">days avg</span>
        </p>
        <p className={`mt-4 text-sm font-semibold ${signedTone(summary.median_return)}`}>
          median return {pct(summary.median_return)}
        </p>
      </div>
    </div>
  );
}

function HorizonTable({ stats }: { stats: BacktestStat[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] border-collapse text-sm">
        <thead>
          <tr className="text-slate-400">
            <th className="px-4 py-2 text-left">보유기간</th>
            <th className="px-4 py-2 text-right">신호 수</th>
            <th className="px-4 py-2 text-right">승률</th>
            <th className="px-4 py-2 text-right">평균</th>
            <th className="px-4 py-2 text-right">중앙값</th>
            <th className="px-4 py-2 text-right">p25 / p75</th>
            <th className="px-4 py-2 text-right">min / max</th>
            <th className="px-4 py-2 text-right">절단</th>
          </tr>
        </thead>
        <tbody>
          {HORIZONS.map((horizon) => {
            const stat = statOf(stats, horizon, 'ALL');
            return (
              <tr className="border-t border-slate-800/70" key={horizon}>
                <td className="px-4 py-3 font-semibold text-slate-200">{horizon}주</td>
                <td className="px-4 py-3 text-right text-slate-300">{count(stat?.count)}</td>
                <td className="px-4 py-3 text-right font-semibold text-slate-50">
                  {ratio(stat?.win_rate ?? null)}
                </td>
                <td className={`px-4 py-3 text-right font-semibold ${signedTone(stat?.mean)}`}>
                  {pct(stat?.mean ?? null)}
                </td>
                <td className={`px-4 py-3 text-right ${signedTone(stat?.median)}`}>
                  {pct(stat?.median ?? null)}
                </td>
                <td className="px-4 py-3 text-right text-slate-400">
                  {pct(stat?.p25 ?? null)} / {pct(stat?.p75 ?? null)}
                </td>
                <td className="px-4 py-3 text-right text-slate-500">
                  {pct(stat?.min ?? null)} / {pct(stat?.max ?? null)}
                </td>
                <td className="px-4 py-3 text-right text-slate-500">
                  {count(stat?.censored_count)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function scoreBuckets(stats: BacktestStat[]): string[] {
  const buckets = new Set(stats.map((stat) => stat.score_bucket));
  if (SIMILARITY_BUCKETS.some((bucket) => buckets.has(bucket))) {
    return [...SIMILARITY_BUCKETS];
  }
  if (buckets.has('8+') || buckets.has('6-7') || buckets.has('4-5')) {
    return [...LEGACY_BUCKETS];
  }
  return [...buckets].filter((bucket) => bucket !== 'ALL').sort();
}

function BucketComparison({ stats }: { stats: BacktestStat[] }) {
  const buckets = useMemo(() => scoreBuckets(stats), [stats]);
  const topWinRateRanks = useMemo(
    () => rankTopWinRateCells(stats, buckets, HORIZONS),
    [buckets, stats],
  );
  const rows = useMemo(
    () =>
      buckets.map((bucket) => ({
        bucket,
        stats: HORIZONS.map((horizon) => statOf(stats, horizon, bucket)),
      })),
    [buckets, stats],
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="border-b border-amber-100/10 pb-3">
        <p className="text-xs font-semibold uppercase tracking-[0.32em] text-amber-300">
          score buckets
        </p>
        <h3 className="mt-2 text-xl font-semibold tracking-tight text-slate-50">
          점수 구간별 승률
        </h3>
      </div>

      <div className="grid gap-3">
        {rows.map(({ bucket, stats: bucketStats }) => (
          <div
            className="grid gap-3 rounded-lg border border-slate-800/80 bg-slate-950/50 p-4 lg:grid-cols-[72px_repeat(4,minmax(0,1fr))]"
            key={bucket}
          >
            <div className="flex items-center">
              <span className="rounded-md bg-amber-300 px-2.5 py-1 text-sm font-semibold text-slate-950">
                {bucket}
              </span>
            </div>
            {HORIZONS.map((horizon, index) => {
              const stat = bucketStats[index];
              const winRate = stat?.win_rate ?? null;
              const width = winRate === null ? 0 : Math.max(0, Math.min(100, winRate * 100));
              const rank = topWinRateRanks.get(bucketHorizonKey(bucket, horizon));
              const isTopRank = rank !== undefined;
              return (
                <div
                  className={[
                    'flex min-w-0 flex-col gap-2 rounded-md border p-2 transition-colors',
                    isTopRank
                      ? 'border-amber-200/40 bg-amber-300/10 shadow-[0_0_0_1px_rgba(252,211,77,0.08)]'
                      : 'border-transparent',
                  ].join(' ')}
                  key={horizon}
                >
                  <div className="flex items-center justify-between gap-3 text-xs">
                    <span className="font-semibold text-slate-300">{horizon}주</span>
                    <span className="text-slate-500">n={count(stat?.count)}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                    <div
                      className={[
                        'h-full rounded-full transition-[width]',
                        isTopRank ? 'bg-amber-200' : 'bg-amber-300',
                      ].join(' ')}
                      style={{ width: `${width}%` }}
                    />
                  </div>
                  <div className="flex items-center justify-between gap-3 text-xs">
                    <span className="flex items-center gap-1.5 font-semibold text-slate-100">
                      {ratio(winRate)}
                      {rank !== undefined && (
                        <span className="rounded-full border border-amber-200/40 bg-slate-950/70 px-1.5 py-0.5 text-[10px] font-bold leading-none text-amber-200">
                          #{rank}
                        </span>
                      )}
                    </span>
                    <span className={signedTone(stat?.mean)}>{pct(stat?.mean ?? null)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function BacktestPage() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const runIdParam = searchParams.get('runId');
  const requestedRunId = runIdParam === null ? NaN : Number(runIdParam);
  const lastAppliedSearch = useRef<string | null>(null);
  const {
    data: runs = [],
    isError: runsError,
    isLoading: runsLoading,
    refetch: refetchRuns,
  } = useQuery({
    queryKey: ['backtest', 'runs'],
    queryFn: fetchBacktestRuns,
  });
  const [runId, setRunId] = useState<number | null>(null);

  useEffect(() => {
    if (runs.length === 0) {
      return;
    }

    const searchChanged = lastAppliedSearch.current !== location.search;
    if (!searchChanged && runId !== null) {
      return;
    }

    const requested = Number.isInteger(requestedRunId)
      ? runs.find((run) => run.id === requestedRunId)
      : undefined;

    setRunId(requested?.id ?? runs[0].id);
    lastAppliedSearch.current = location.search;
  }, [runs, runId, requestedRunId, location.search]);

  useEffect(() => {
    if (
      runs.length > 0 &&
      runId !== null &&
      !runs.some((run) => run.id === runId)
    ) {
      setRunId(runs[0].id);
    }
  }, [runs, runId]);

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

  const retry = () => {
    void refetchRuns();
    if (runId !== null) void refetchDetail();
  };

  return (
    <section className="flex flex-col gap-10">
      <div className="border-b border-amber-100/10 pb-4">
        <p className="text-xs font-semibold uppercase tracking-[0.32em] text-amber-300">
          backtest
        </p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-50">
          룰 신호 백테스트
        </h2>
      </div>

      {runsError || detailError ? (
        <ErrorPanel onRetry={retry} />
      ) : runsLoading ? (
        <LoadingBlock className="h-16" />
      ) : runs.length === 0 ? (
        <EmptyState />
      ) : (
        <>
          <RunSelector
            detail={detail}
            runId={runId}
            runs={runs}
            onChange={setRunId}
          />

          {detailLoading || !detail ? (
            <div className="flex flex-col gap-4">
              <LoadingBlock className="h-28" />
              <LoadingBlock className="h-64" />
            </div>
          ) : (
            <>
              <SummaryStrip detail={detail} />
              {detail.strategy_kind === 'analysis_contract' && detail.event_summary ? (
                <ContractEventSummaryPanel summary={detail.event_summary} />
              ) : (
                <>
                  <HorizonTable stats={detail.stats} />
                  {detail.stats.length > 0 && <BucketComparison stats={detail.stats} />}
                </>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}

export default BacktestPage;
