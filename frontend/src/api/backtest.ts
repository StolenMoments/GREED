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
  source_analysis_id: number | null;
  strategy_kind: string | null;
  similarity_threshold: number | null;
  notes: string | null;
  source_ticker: string | null;
  source_name: string | null;
}

export interface BacktestEventSummary {
  signal_count: number;
  entered_count: number;
  no_entry_count: number;
  target_count: number;
  stop_count: number;
  expiry_count: number;
  target_hit_rate: number | null;
  positive_return_rate: number | null;
  win_rate: number | null;
  mean_return: number | null;
  median_return: number | null;
  avg_days_held: number | null;
}

export interface BacktestRunDetail extends BacktestRunSummary {
  stats: BacktestStat[];
  event_summary: BacktestEventSummary | null;
}

export async function fetchBacktestRuns(): Promise<BacktestRunSummary[]> {
  const response = await apiClient.get<BacktestRunSummary[]>('/backtest/runs');
  return response.data;
}

export async function fetchBacktestRun(id: number): Promise<BacktestRunDetail> {
  const response = await apiClient.get<BacktestRunDetail>(`/backtest/runs/${id}`);
  return response.data;
}
