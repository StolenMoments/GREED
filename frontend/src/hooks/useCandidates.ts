import { useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchCandidates,
  fetchLatestScanJob,
  fetchScanJob,
  triggerScan,
} from '../api/candidates';
import type { CandidateScanJob } from '../types';

export const candidateKeys = {
  all: ['candidates'] as const,
  scanJobs: (analysisId: number) =>
    [...candidateKeys.all, 'scan-jobs', analysisId] as const,
  scanJob: (analysisId: number, jobId: number) =>
    [...candidateKeys.scanJobs(analysisId), jobId] as const,
  list: (analysisId: number, minScore: number) =>
    [...candidateKeys.all, 'list', analysisId, minScore] as const,
};

export function useTriggerScan() {
  return useMutation<
    CandidateScanJob,
    Error,
    { analysisId: number; threshold: number }
  >({
    mutationFn: ({ analysisId, threshold }) =>
      triggerScan(analysisId, { threshold }),
  });
}

export function useScanJobPolling(
  analysisId: number | undefined,
  jobId: number | null,
) {
  const queryClient = useQueryClient();
  const invalidatedRef = useRef<number | null>(null);

  const query = useQuery({
    queryKey: candidateKeys.scanJob(analysisId ?? 0, jobId ?? 0),
    queryFn: () => fetchScanJob(analysisId as number, jobId as number),
    enabled: analysisId !== undefined && jobId !== null,
    refetchInterval: (pollingQuery) => {
      const status = pollingQuery.state.data?.status;
      return status === 'pending' || status === 'running' ? 2000 : false;
    },
  });

  useEffect(() => {
    const job = query.data;
    if (!job || job.status !== 'done') return;
    if (invalidatedRef.current === job.id) return;

    invalidatedRef.current = job.id;
    if (analysisId !== undefined) {
      void queryClient.invalidateQueries({
        queryKey: candidateKeys.list(analysisId, job.threshold),
      });
    }
  }, [query.data, queryClient, analysisId]);

  useEffect(() => {
    invalidatedRef.current = null;
  }, [jobId]);

  return query;
}

export function useCandidates(
  analysisId: number | undefined,
  minScore: number,
) {
  return useQuery({
    queryKey: candidateKeys.list(analysisId ?? 0, minScore),
    queryFn: () => fetchCandidates(analysisId as number, minScore),
    enabled: analysisId !== undefined,
  });
}

export function useLatestScanJob(analysisId: number | undefined) {
  return useQuery({
    queryKey: candidateKeys.scanJobs(analysisId ?? 0),
    queryFn: () => fetchLatestScanJob(analysisId as number),
    enabled: analysisId !== undefined,
  });
}
