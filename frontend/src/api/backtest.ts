import { apiClient } from './client';

export interface BacktestStat {
  horizon: number;
  score_bucket: string;
  count: number;
  censored_count: number;
  win_rate: number | null;
  mean: number | null;
  median: number | null;
  std: number | null;
  p25: number | null;
  p75: number | null;
  min: number | null;
  max: number | null;
}

export interface BacktestRunSummary {
  id: number;
  created_at: string;
  universe: string;
  buy_threshold: number;
  horizons: string;
  warmup_weeks: number;
  data_start: string | null;
  data_end: string | null;
  ticker_count: number;
  signal_count: number;
  notes: string | null;
}

export interface BacktestRunDetail extends BacktestRunSummary {
  stats: BacktestStat[];
}

export async function fetchBacktestRuns(): Promise<BacktestRunSummary[]> {
  const response = await apiClient.get<BacktestRunSummary[]>('/backtest/runs');
  return response.data;
}

export async function fetchBacktestRun(id: number): Promise<BacktestRunDetail> {
  const response = await apiClient.get<BacktestRunDetail>(`/backtest/runs/${id}`);
  return response.data;
}
