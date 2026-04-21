import { useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchJob, fetchJobs, triggerAnalysis } from '../api/jobs';
import type { Job, JobTriggerRequest } from '../types';
import { analysisKeys } from './useAnalyses';
import { runKeys } from './useRuns';

export const jobKeys = {
  all: ['jobs'] as const,
  lists: () => [...jobKeys.all, 'list'] as const,
  list: (runId: number) => [...jobKeys.lists(), 'run', runId] as const,
  detail: (jobId: number) => [...jobKeys.all, 'detail', jobId] as const,
};

export function useTriggerAnalysis() {
  const queryClient = useQueryClient();

  return useMutation<Job, Error, JobTriggerRequest>({
    mutationFn: triggerAnalysis,
    onSuccess: (job) => {
      void queryClient.invalidateQueries({ queryKey: jobKeys.list(job.run_id) });
      queryClient.setQueryData(jobKeys.detail(job.id), job);
    },
  });
}

export function useRunJobs(runId: number | undefined) {
  return useQuery({
    queryKey: jobKeys.list(runId ?? 0),
    queryFn: () => fetchJobs(runId),
    enabled: runId !== undefined,
  });
}

export function useJobPolling(jobId: number | null) {
  const queryClient = useQueryClient();
  const invalidatedJobIdRef = useRef<number | null>(null);
  const query = useQuery({
    queryKey: jobKeys.detail(jobId ?? 0),
    queryFn: () => fetchJob(jobId as number),
    enabled: jobId !== null,
    refetchInterval: (pollingQuery) => {
      const status = pollingQuery.state.data?.status;
      return status === 'pending' ? 2000 : false;
    },
  });

  useEffect(() => {
    const job = query.data;
    if (!job || job.status !== 'done') {
      return;
    }

    if (invalidatedJobIdRef.current === job.id) {
      return;
    }

    invalidatedJobIdRef.current = job.id;
    void queryClient.invalidateQueries({ queryKey: jobKeys.list(job.run_id) });
    void queryClient.invalidateQueries({ queryKey: analysisKeys.lists() });
    void queryClient.invalidateQueries({ queryKey: runKeys.lists() });
    void queryClient.invalidateQueries({ queryKey: runKeys.detail(job.run_id) });
  }, [query.data, queryClient]);

  useEffect(() => {
    invalidatedJobIdRef.current = null;
  }, [jobId]);

  return query;
}
