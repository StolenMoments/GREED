import { renderToStaticMarkup } from 'react-dom/server';
import React from 'react';

import type {
  DailyRallyInsights,
  DailyRallyPatternStats,
} from '../api/backtest';
import {
  DailyRallyPatternBriefing,
  DailyRallyPatternStatsTable,
} from './DailyRallyPanels';

const emptyInsights: DailyRallyInsights = {
  run_id: 1,
  rule_count: 0,
  rules: [],
};

const patternStats: DailyRallyPatternStats = {
  run_id: 1,
  pattern_count: 1,
  patterns: [
    {
      id: 10,
      run_id: 1,
      pattern_key: 'ret_20d>=0.20',
      pattern_label: 'ret_20d >= 0.20',
      support: 2,
      positives: 2,
      total_matches: 3,
      precision: 2 / 3,
      base_rate: 0.25,
      lift: (2 / 3) / 0.25,
      score: 2.2,
      return_stats: [
        {
          horizon: 20,
          count: 3,
          censored_count: 0,
          win_rate: 2 / 3,
          mean: 0.2,
          median: 0.1,
          std: 0.3,
          p25: 0.0,
          p75: 0.35,
          min: -0.1,
          max: 0.5,
        },
        {
          horizon: 40,
          count: 2,
          censored_count: 1,
          win_rate: 1,
          mean: 0.35,
          median: 0.35,
          std: 0.05,
          p25: 0.325,
          p75: 0.375,
          min: 0.3,
          max: 0.4,
        },
      ],
    },
  ],
};

const briefing = renderToStaticMarkup(
  <DailyRallyPatternBriefing
    insights={emptyInsights}
    isError={false}
    patternStats={patternStats}
    patternStatsIsError={false}
  />,
);

if (!briefing.includes('ret_20d')) {
  throw new Error('Pattern briefing should fall back to pattern stats when strict rules are empty');
}

if (!briefing.includes('66.7%') || !briefing.includes('2.67')) {
  throw new Error('Pattern briefing should show pattern precision and lift');
}

const table = renderToStaticMarkup(
  <DailyRallyPatternStatsTable isError={false} patternStats={patternStats} />,
);

for (const expected of ['Pattern Stats', '3', '66.7%', '25.0%', '2.67', '+20.0%', '+35.0%']) {
  if (!table.includes(expected)) {
    throw new Error(`Pattern stats table should include ${expected}`);
  }
}

const failedTable = renderToStaticMarkup(
  <DailyRallyPatternStatsTable isError={true} patternStats={undefined} />,
);

if (!failedTable.includes('Could not load')) {
  throw new Error('Pattern stats API failure should render a local table error only');
}
