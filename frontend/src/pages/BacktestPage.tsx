import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import {
  fetchBacktestRun,
  fetchBacktestRuns,
  type BacktestRunSummary,
  type BacktestRunDetail,
  type BacktestStat,
} from '../api/backtest';

const HORIZONS = [4, 8, 12, 26] as const;
const BUCKETS = ['4-5', '6-7', '8+'] as const;

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
  return (
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <span className="text-sm text-slate-400">실행 선택</span>
        <select
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 transition focus:outline-none focus:ring-1 focus:ring-amber-400/60"
          value={runId ?? ''}
          onChange={(event) => onChange(Number(event.target.value))}
        >
          {runs.map((run) => (
            <option key={run.id} value={run.id}>
              #{run.id} · {date(run.created_at)} · 신호 {run.signal_count.toLocaleString('ko-KR')}
            </option>
          ))}
        </select>
      </div>

      {detail && (
        <div className="text-right text-xs text-slate-500">
          <p>
            {detail.universe} · 종목 {detail.ticker_count.toLocaleString('ko-KR')}개 ·
            기준점 {detail.buy_threshold}
          </p>
          <p className="mt-1">
            {date(detail.data_start)} ~ {date(detail.data_end)} · 워밍업 {detail.warmup_weeks}주
          </p>
        </div>
      )}
    </div>
  );
}

function SummaryStrip({ detail }: { detail: BacktestRunDetail }) {
  const allStats = detail.stats.filter((stat) => stat.score_bucket === 'ALL');
  const signalCount = Math.max(...allStats.map((stat) => stat.count), detail.signal_count, 0);
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

function BucketComparison({ stats }: { stats: BacktestStat[] }) {
  const rows = useMemo(
    () =>
      BUCKETS.map((bucket) => ({
        bucket,
        stats: HORIZONS.map((horizon) => statOf(stats, horizon, bucket)),
      })),
    [stats],
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
              return (
                <div className="flex min-w-0 flex-col gap-2" key={horizon}>
                  <div className="flex items-center justify-between gap-3 text-xs">
                    <span className="font-semibold text-slate-300">{horizon}주</span>
                    <span className="text-slate-500">n={count(stat?.count)}</span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                    <div
                      className="h-full rounded-full bg-amber-300 transition-[width]"
                      style={{ width: `${width}%` }}
                    />
                  </div>
                  <div className="flex items-center justify-between gap-3 text-xs">
                    <span className="font-semibold text-slate-100">{ratio(winRate)}</span>
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
    if (runs.length > 0 && runId === null) {
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
              <HorizonTable stats={detail.stats} />
              {detail.stats.length > 0 && <BucketComparison stats={detail.stats} />}
            </>
          )}
        </>
      )}
    </section>
  );
}

export default BacktestPage;
