import { useQuery } from '@tanstack/react-query';
import client from './client';
import type { StockSummary } from './types';

export function useStocks() {
  return useQuery<StockSummary[]>({
    queryKey: ['stocks'],
    queryFn: async () => {
      const { data } = await client.get<StockSummary[]>('/stocks/summary');
      return data;
    },
  });
}
