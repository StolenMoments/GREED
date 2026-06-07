import type { BacktestStat } from '../api/backtest';
import {
  bucketHorizonKey,
  formatHorizonLabel,
  formatScoreBucketLabel,
  rankTopWinRateCells,
} from './backtestHighlights';

function stat(
  horizon: number,
  scoreBucket: string,
  winRate: number | null,
  count: number,
): BacktestStat {
  return {
    horizon,
    score_bucket: scoreBucket,
    count,
    censored_count: 0,
    win_rate: winRate,
    mean: null,
    median: null,
    std: null,
    p25: null,
    p75: null,
    min: null,
    max: null,
  };
}

const ranks = rankTopWinRateCells(
  [
    stat(4, '10', 0.7, 4),
    stat(8, '10', 0.9, 2),
    stat(12, '10', null, 20),
    stat(4, '11', 0.9, 5),
    stat(8, '11', 0.65, 100),
    stat(12, '11', 0.8, 3),
    stat(4, '12', 0.9, 5),
    stat(8, '12', 0.4, 10),
  ],
  ['10', '11', '12'],
  [4, 8, 12],
);

const actual = JSON.stringify([...ranks.entries()]);
const expected = JSON.stringify([
  [bucketHorizonKey('11', 4), 1],
  [bucketHorizonKey('12', 4), 2],
  [bucketHorizonKey('10', 8), 3],
]);

if (actual !== expected) {
  throw new Error(`Expected top ranks ${expected}, received ${actual}`);
}

if (ranks.has(bucketHorizonKey('10', 12))) {
  throw new Error('Null win-rate cell should not be ranked');
}

if (formatHorizonLabel({ strategy_kind: 'daily_20d_40pct_rally' }, 20) !== '20d') {
  throw new Error('Daily rally horizon should be formatted in days');
}

if (formatHorizonLabel({ strategy_kind: 'ichimoku_span2_breakout' }, 20) !== '20주') {
  throw new Error('Non-daily-rally horizon should keep weekly label');
}

const bucketLabels = {
  positive: 'Positive Events',
  control: 'Controls',
  ALL: 'All Samples',
  '8+': '8+',
};

for (const [bucket, expectedLabel] of Object.entries(bucketLabels)) {
  const actualLabel = formatScoreBucketLabel(bucket);
  if (actualLabel !== expectedLabel) {
    throw new Error(`Expected ${bucket} bucket label ${expectedLabel}, received ${actualLabel}`);
  }
}
