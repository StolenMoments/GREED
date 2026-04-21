import { apiClient } from './client';
import type {
  Analysis,
  AnalysisFilters,
  AnalysisSummary,
  CreateAnalysisPayload,
} from '../types';

export async function fetchAnalyses(
  runId: number,
  filters: AnalysisFilters = {},
): Promise<AnalysisSummary[]> {
  const response = await apiClient.get<AnalysisSummary[]>(
    `/runs/${runId}/analyses`,
    {
      params: filters,
    },
  );
  return response.data;
}

export async function fetchAnalysis(analysisId: number): Promise<Analysis> {
  const response = await apiClient.get<Analysis>(`/analyses/${analysisId}`);
  return response.data;
}

export async function fetchHistory(
  analysisId: number,
): Promise<AnalysisSummary[]> {
  const response = await apiClient.get<AnalysisSummary[]>(
    `/analyses/${analysisId}/history`,
  );
  return response.data;
}

export async function createAnalysis(
  payload: CreateAnalysisPayload,
): Promise<Analysis> {
  const response = await apiClient.post<Analysis>('/analyses', payload);
  return response.data;
}
