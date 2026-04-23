import { apiClient } from './client';
import type { StockPrice } from '../types';

export async function fetchStockPrice(ticker: string): Promise<StockPrice> {
  const response = await apiClient.get<StockPrice>(`/stock/${ticker}/price`);
  return response.data;
}

export async function refreshStockPrice(ticker: string): Promise<StockPrice> {
  const response = await apiClient.post<StockPrice>(
    `/stock/${ticker}/price/refresh`,
  );
  return response.data;
}
