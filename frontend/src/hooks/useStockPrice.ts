import { useQuery } from '@tanstack/react-query';
import { fetchStockPrice } from '../api/stock';

export function useStockPrice(ticker: string | undefined) {
  return useQuery({
    queryKey: ['stock', 'price', ticker],
    queryFn: () => fetchStockPrice(ticker as string),
    enabled: !!ticker,
    staleTime: 1000 * 60 * 10,
    retry: false,
  });
}
