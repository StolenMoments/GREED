import { apiClient } from './client';

export interface TickerSearchResult {
  code: string;
  name: string;
}

export async function searchTickers(q: string): Promise<TickerSearchResult[]> {
  const res = await apiClient.get<TickerSearchResult[]>('/tickers/search', { params: { q } });
  return res.data;
}
