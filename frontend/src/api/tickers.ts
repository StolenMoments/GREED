import { apiClient } from './client';

export interface TickerSearchResult {
  code: string;
  name: string;
  market: 'KR' | 'US';
}

export async function searchTickers(q: string): Promise<TickerSearchResult[]> {
  const res = await apiClient.get<TickerSearchResult[]>('/tickers/search', { params: { q } });
  return res.data;
}

export async function getTicker(code: string): Promise<TickerSearchResult> {
  const res = await apiClient.get<TickerSearchResult>(`/tickers/${code}`);
  return res.data;
}
