import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchStockPrice, refreshStockPrice } from '../api/stock';
import { analysisKeys } from './useAnalyses';

export const stockPriceKeys = {
  all: ['stock'] as const,
  prices: () => [...stockPriceKeys.all, 'price'] as const,
  price: (ticker: string) => [...stockPriceKeys.prices(), ticker] as const,
};

export function useStockPrice(ticker: string | undefined) {
  return useQuery({
    queryKey: stockPriceKeys.price(ticker ?? ''),
    queryFn: () => fetchStockPrice(ticker as string),
    enabled: !!ticker,
    staleTime: 1000 * 60 * 10,
    retry: false,
  });
}

export function useRefreshStockPrice(ticker: string | undefined) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => refreshStockPrice(ticker as string),
    onSuccess: (stockPrice) => {
      if (!ticker) {
        return;
      }

      queryClient.setQueryData(stockPriceKeys.price(ticker), stockPrice);
      queryClient.invalidateQueries({ queryKey: analysisKeys.lists() });
    },
  });
}
