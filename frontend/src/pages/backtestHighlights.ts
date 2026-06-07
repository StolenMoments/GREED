import type { BacktestStat } from '../api/backtest';

export function bucketHorizonKey(bucket: string, horizon: number): string {
  return `${bucket}:${horizon}`;
}

export function formatHorizonLabel(
  detail: Pick<{ strategy_kind: string | null }, 'strategy_kind'>,
  horizon: number,
): string {
  if (detail.strategy_kind === 'daily_20d_40pct_rally') {
    return `${horizon}d`;
  }
  return `${horizon}주`;
}

export function formatScoreBucketLabel(bucket: string): string {
  if (bucket === 'positive') return 'Positive Events';
  if (bucket === 'control') return 'Controls';
  if (bucket === 'ALL') return 'All Samples';
  return bucket;
}

export function rankTopWinRateCells(
  stats: BacktestStat[],
  buckets: readonly string[],
  horizons: readonly number[],
  limit = 3,
): Map<string, number> {
  const candidates = buckets.flatMap((bucket, bucketIndex) =>
    horizons.flatMap((horizon, horizonIndex) => {
      const stat = stats.find(
        (item) => item.score_bucket === bucket && item.horizon === horizon,
      );
      if (!stat || stat.win_rate === null) {
        return [];
      }
      return [
        {
          key: bucketHorizonKey(bucket, horizon),
          winRate: stat.win_rate,
          count: stat.count,
          displayOrder: bucketIndex * horizons.length + horizonIndex,
        },
      ];
    }),
  );

  candidates.sort((left, right) => {
    if (right.winRate !== left.winRate) return right.winRate - left.winRate;
    if (right.count !== left.count) return right.count - left.count;
    return left.displayOrder - right.displayOrder;
  });

  return new Map(
    candidates.slice(0, limit).map((candidate, index) => [candidate.key, index + 1]),
  );
}
