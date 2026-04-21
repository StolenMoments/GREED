import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createAnalysis,
  fetchAllAnalyses,
  fetchAnalyses,
  fetchAnalysis,
  fetchHistory,
} from '../api/analyses';
import { runKeys } from './useRuns';
import type { AnalysisFilters, CreateAnalysisPayload } from '../types';

export const analysisKeys = {
  all: ['analyses'] as const,
  lists: () => [...analysisKeys.all, 'list'] as const,
  list: (runId: number, filters: AnalysisFilters = {}) =>
    [...analysisKeys.lists(), 'run', runId, filters] as const,
  globalList: (filters: AnalysisFilters = {}) =>
    [...analysisKeys.lists(), 'all', filters] as const,
  details: () => [...analysisKeys.all, 'detail'] as const,
  detail: (analysisId: number) =>
    [...analysisKeys.details(), analysisId] as const,
  history: (analysisId: number) =>
    [...analysisKeys.detail(analysisId), 'history'] as const,
};

export function useAnalyses(
  runId: number | undefined,
  filters: AnalysisFilters = {},
) {
  return useQuery({
    queryKey: analysisKeys.list(runId ?? 0, filters),
    queryFn: () => fetchAnalyses(runId as number, filters),
    enabled: runId !== undefined,
  });
}

export function useAllAnalyses(filters: AnalysisFilters = {}) {
  return useQuery({
    queryKey: analysisKeys.globalList(filters),
    queryFn: () => fetchAllAnalyses(filters),
  });
}

export function useAnalysis(analysisId: number | undefined) {
  return useQuery({
    queryKey: analysisKeys.detail(analysisId ?? 0),
    queryFn: () => fetchAnalysis(analysisId as number),
    enabled: analysisId !== undefined,
  });
}

export function useHistory(analysisId: number | undefined) {
  return useQuery({
    queryKey: analysisKeys.history(analysisId ?? 0),
    queryFn: () => fetchHistory(analysisId as number),
    enabled: analysisId !== undefined,
  });
}

export function useCreateAnalysis() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreateAnalysisPayload) => createAnalysis(payload),
    onSuccess: (analysis) => {
      queryClient.invalidateQueries({ queryKey: analysisKeys.lists() });
      queryClient.invalidateQueries({ queryKey: runKeys.lists() });
      queryClient.invalidateQueries({ queryKey: runKeys.detail(analysis.run_id) });
      queryClient.setQueryData(analysisKeys.detail(analysis.id), analysis);
    },
  });
}
