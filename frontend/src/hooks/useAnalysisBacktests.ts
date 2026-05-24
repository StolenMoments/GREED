import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchAnalysisBacktestJob,
  fetchAnalysisBacktestJobs,
  triggerAnalysisBacktest,
} from '../api/analysisBacktests';
import type { AnalysisBacktestJob, AnalysisBacktestJobCreate } from '../types';

export const analysisBacktestKeys = {
  all: ['analysis-backtests'] as const,
  list: (analysisId: number) =>
    [...analysisBacktestKeys.all, 'analysis', analysisId] as const,
  detail: (analysisId: number, jobId: number) =>
    [...analysisBacktestKeys.list(analysisId), 'job', jobId] as const,
};

function isActive(job: AnalysisBacktestJob | undefined): boolean {
  return job?.status === 'pending' || job?.status === 'running';
}

export function useAnalysisBacktestJobs(analysisId: number | undefined) {
  return useQuery({
    queryKey: analysisBacktestKeys.list(analysisId ?? 0),
    queryFn: () => fetchAnalysisBacktestJobs(analysisId as number),
    enabled: analysisId !== undefined,
    refetchInterval: (query) => {
      const jobs = query.state.data;
      return jobs?.some(isActive) ? 2000 : false;
    },
  });
}

export function useAnalysisBacktestJob(
  analysisId: number | undefined,
  jobId: number | undefined,
) {
  return useQuery({
    queryKey: analysisBacktestKeys.detail(analysisId ?? 0, jobId ?? 0),
    queryFn: () =>
      fetchAnalysisBacktestJob(analysisId as number, jobId as number),
    enabled: analysisId !== undefined && jobId !== undefined,
    refetchInterval: (query) => (isActive(query.state.data) ? 2000 : false),
  });
}

export function useTriggerAnalysisBacktest(analysisId: number | undefined) {
  const queryClient = useQueryClient();

  return useMutation<AnalysisBacktestJob, Error, AnalysisBacktestJobCreate>({
    mutationFn: (payload) =>
      triggerAnalysisBacktest(analysisId as number, payload),
    onSuccess: (job) => {
      if (analysisId !== undefined) {
        queryClient.setQueryData(
          analysisBacktestKeys.detail(analysisId, job.id),
          job,
        );
        void queryClient.invalidateQueries({
          queryKey: analysisBacktestKeys.list(analysisId),
        });
      }
      void queryClient.invalidateQueries({ queryKey: ['backtest'] });
    },
  });
}
