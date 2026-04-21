import { useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchJob, triggerAnalysis } from '../api/jobs';
import type { Job, JobTriggerRequest } from '../types';
import { analysisKeys } from './useAnalyses';
import { runKeys } from './useRuns';

export const jobKeys = {
  all: ['jobs'] as const,
  detail: (jobId: number) => [...jobKeys.all, 'detail', jobId] as const,
};

export function useTriggerAnalysis() {
  const queryClient = useQueryClient();

  return useMutation<Job, Error, JobTriggerRequest>({
    mutationFn: triggerAnalysis,
    onSuccess: (job) => {
      queryClient.setQueryData(jobKeys.detail(job.id), job);
    },
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
    void queryClient.invalidateQueries({ queryKey: analysisKeys.lists() });
    void queryClient.invalidateQueries({ queryKey: runKeys.lists() });
    void queryClient.invalidateQueries({ queryKey: runKeys.detail(job.run_id) });
  }, [query.data, queryClient]);

  useEffect(() => {
    invalidatedJobIdRef.current = null;
  }, [jobId]);

  return query;
}
