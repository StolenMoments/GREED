import { useQuery } from '@tanstack/react-query';
import { fetchStockSummary } from '../api/stocks';

export const stockKeys = {
  summary: ['stocks', 'summary'] as const,
};

export function useStockSummary() {
  return useQuery({
    queryKey: stockKeys.summary,
    queryFn: fetchStockSummary,
  });
}
