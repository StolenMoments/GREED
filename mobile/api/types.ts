export type Judgment = '매수' | '홀드' | '매도';

export interface AnalysisItem {
  id: number;
  ticker: string;
  name: string;
  judgment: Judgment;
  trend: string;
  cloud_position: string;
  ma_alignment: string;
  created_at: string;
  entry_price:      number | null;
  entry_price_max:  number | null;
  target_price:     number | null;
  target_price_max: number | null;
  stop_loss:          number | null;
  stop_loss_max:      number | null;
  current_price:      number | null;
  current_price_date: string | null;
}

export interface AnalysisDetail extends AnalysisItem {
  markdown: string;
}

export interface AnalysesPage {
  items: AnalysisItem[];
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

export interface StockSummary {
  ticker: string;
  name: string;
  buy_count: number;
  hold_count: number;
  sell_count: number;
  latest_at: string;
}
