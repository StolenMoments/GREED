import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createRun, fetchRun, fetchRuns } from '../api/runs';
import type { CreateRunPayload } from '../types';

export const runKeys = {
  all: ['runs'] as const,
  lists: () => [...runKeys.all, 'list'] as const,
  detail: (runId: number) => [...runKeys.all, 'detail', runId] as const,
};

export function useRuns() {
  return useQuery({
    queryKey: runKeys.lists(),
    queryFn: fetchRuns,
  });
}

export function useRun(runId: number | undefined) {
  return useQuery({
    queryKey: runKeys.detail(runId ?? 0),
    queryFn: () => fetchRun(runId as number),
    enabled: runId !== undefined,
  });
}

export function useCreateRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreateRunPayload = {}) => createRun(payload),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: runKeys.lists() });
      queryClient.setQueryData(runKeys.detail(run.id), run);
    },
  });
}
