import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import client from './client';
import type { AnalysesPage, AnalysisDetail, Judgment } from './types';

interface AnalysesParams {
  judgment?: Judgment | null;
  q?: string;
}

export function useInfiniteAnalyses({ judgment, q }: AnalysesParams = {}) {
  return useInfiniteQuery<AnalysesPage>({
    queryKey: ['analyses', judgment ?? null, q ?? ''],
    queryFn: async ({ pageParam }) => {
      const { data } = await client.get<AnalysesPage>('/analyses', {
        params: {
          page:      pageParam,
          per_page:  20,
          judgment:  judgment ?? undefined,
          q:         q || undefined,
        },
      });
      return data;
    },
    initialPageParam: 1,
    getNextPageParam: (last) =>
      last.page < last.total_pages ? last.page + 1 : undefined,
  });
}

export function useAnalysis(id: number | null) {
  return useQuery<AnalysisDetail>({
    queryKey: ['analysis', id],
    queryFn: async () => {
      const { data } = await client.get<AnalysisDetail>(`/analyses/${id}`);
      return data;
    },
    enabled: id != null,
  });
}
