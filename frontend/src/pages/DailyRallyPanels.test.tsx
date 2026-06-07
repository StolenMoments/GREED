import { renderToStaticMarkup } from 'react-dom/server';
import React from 'react';

import type {
  DailyRallyInsights,
  DailyRallyPatternStats,
  DailyRallyValidation,
} from '../api/backtest';
import {
  DailyRallyPatternBriefing,
  DailyRallyPatternStatsTable,
  DailyRallyValidationPanel,
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

const validation: DailyRallyValidation = {
  run_id: 1,
  summary: {
    sample_count: 120,
    complete_years: [2015, 2016, 2017, 2018],
    partial_years: [2026],
    top_positive_ticker_share: 0.28,
    walk_forward_median_lift: 1.35,
  },
  year_breakdown: [
    {
      year: 2026,
      total: 18,
      positives: 3,
      base_rate: 1 / 6,
      positive_forward_return_120d_mean: null,
      censored_120d_count: 18,
      partial: true,
    },
  ],
  ticker_concentration: [
    {
      ticker: '005930',
      name: 'Samsung',
      total_count: 10,
      positive_count: 4,
      positive_share: 0.28,
    },
  ],
  pattern_stability: [
    {
      pattern_key: 'ret_20d>=0.20',
      pattern_label: 'ret_20d >= 0.20',
      total_matches: 20,
      positives: 8,
      full_period_lift: 1.8,
      test_window_count: 5,
      median_train_lift: 1.5,
      median_test_lift: 1.35,
      test_lift_gt_1_ratio: 0.8,
      classification: 'stable',
    },
  ],
  walk_forward_windows: [
    {
      train_years: [2015, 2016, 2017],
      test_year: 2018,
      pattern_key: 'ret_20d>=0.20',
      pattern_label: 'ret_20d >= 0.20',
      train_support: 5,
      train_total_matches: 12,
      train_precision: 0.42,
      train_base_rate: 0.2,
      train_lift: 2.1,
      test_matches: 4,
      test_positives: 1,
      test_precision: 0.25,
      test_base_rate: 0.2,
      test_lift: 1.25,
      classification: 'stable',
    },
  ],
  warnings: ['2026 has censored 120d returns and is excluded from stability checks.'],
};

const validationPanel = renderToStaticMarkup(
  <DailyRallyValidationPanel isError={false} validation={validation} />,
);

for (const expected of ['Validation', '2015 ~ 2018', '2026', '28.0%', '1.35', 'Samsung', 'stable']) {
  if (!validationPanel.includes(expected)) {
    throw new Error(`Validation panel should include ${expected}`);
  }
}

const failedValidation = renderToStaticMarkup(
  <DailyRallyValidationPanel isError={true} validation={undefined} />,
);

if (!failedValidation.includes('Could not load')) {
  throw new Error('Validation API failure should render a local panel error');
}
