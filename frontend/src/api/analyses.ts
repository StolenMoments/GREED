import { apiClient } from './client';
import type {
  Analysis,
  AnalysisFilters,
  AnalysisPaginationParams,
  AnalysisSummary,
  CreateAnalysisPayload,
  PaginatedResponse,
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

export async function fetchAllAnalyses(
  filters: AnalysisFilters = {},
  pagination: AnalysisPaginationParams = { page: 1, page_size: 25 },
): Promise<PaginatedResponse<AnalysisSummary>> {
  const response = await apiClient.get<PaginatedResponse<AnalysisSummary>>(
    '/analyses',
    {
      params: { ...filters, ...pagination },
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

export async function deleteAnalysis(analysisId: number): Promise<void> {
  await apiClient.delete(`/analyses/${analysisId}`);
}

export async function evaluateOutcomes(force = false): Promise<{ evaluated: number; skipped: number }> {
  const response = await apiClient.post<{ evaluated: number; skipped: number }>(
    '/analyses/evaluate-outcomes',
    undefined,
    { params: { force } },
  );
  return response.data;
}

export async function evaluateAnalysisOutcome(analysisId: number): Promise<Analysis> {
  const response = await apiClient.post<Analysis>(
    `/analyses/${analysisId}/evaluate-outcome`,
  );
  return response.data;
}
