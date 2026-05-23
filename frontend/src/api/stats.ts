import { apiClient } from './client';

export interface ModelStat {
  model: string;
  total: number;
  judgments: Record<string, number>;
  outcomes: Record<string, number>;
  win_rate: number | null;
  expectancy_pct: number | null;
  avg_holding_weeks: number | null;
}

export interface HeadToHeadModelRow {
  model: string;
  buy: number;
  hits: number;
  stops: number;
  expectancy_pct: number | null;
}

export interface HeadToHeadStat {
  run_id: number | null;
  tickers: number;
  matrix: HeadToHeadModelRow[];
  agreement: Record<string, number>;
}

export interface SignalCell {
  cloud_position: string;
  ma_alignment: string;
  count: number;
  win_rate: number | null;
  expectancy_pct: number | null;
}

export interface SignalMatrixStat {
  model: string;
  cells: SignalCell[];
}

export async function fetchStatsByModel(): Promise<ModelStat[]> {
  const response = await apiClient.get<ModelStat[]>('/stats/by-model');
  return response.data;
}

export async function fetchHeadToHead(runId: number): Promise<HeadToHeadStat> {
  const response = await apiClient.get<HeadToHeadStat>('/stats/head-to-head', {
    params: { run_id: runId },
  });
  return response.data;
}

export async function fetchBySignal(model: string): Promise<SignalMatrixStat> {
  const response = await apiClient.get<SignalMatrixStat>('/stats/by-signal', {
    params: { model },
  });
  return response.data;
}
