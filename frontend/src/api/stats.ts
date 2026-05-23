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

export async function fetchStatsByModel(): Promise<ModelStat[]> {
  const response = await apiClient.get<ModelStat[]>('/stats/by-model');
  return response.data;
}
