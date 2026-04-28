import { apiClient } from './client';
import type { StockSummary } from '../types';

export async function fetchStockSummary(): Promise<StockSummary[]> {
  const response = await apiClient.get<StockSummary[]>('/stocks/summary');
  return response.data;
}
