export type Judgment = '매수' | '홀드' | '매도';

export type Trend = '상승' | '하락' | '횡보';

export type CloudPosition = '구름 위' | '구름 안' | '구름 아래';

export type MaAlignment = '정배열' | '역배열' | '혼조';

export interface Run {
  id: number;
  memo: string | null;
  created_at: string;
  analysis_count: number;
}

export interface AnalysisSummary {
  id: number;
  run_id: number;
  ticker: string;
  name: string;
  model: string;
  judgment: Judgment;
  trend: Trend;
  cloud_position: CloudPosition;
  ma_alignment: MaAlignment;
  created_at: string;
}

export interface Analysis extends AnalysisSummary {
  markdown: string;
  entry_price: number | null;
  entry_price_max: number | null;
  target_price: number | null;
  target_price_max: number | null;
  stop_loss: number | null;
  stop_loss_max: number | null;
}

export interface CreateRunPayload {
  memo?: string | null;
}

export interface CreateAnalysisPayload {
  run_id: number;
  ticker: string;
  name: string;
  model: string;
  markdown: string;
  judgment: Judgment;
  trend: Trend;
  cloud_position: CloudPosition;
  ma_alignment: MaAlignment;
  entry_price?: number | null;
  entry_price_max?: number | null;
  target_price?: number | null;
  target_price_max?: number | null;
  stop_loss?: number | null;
  stop_loss_max?: number | null;
}

export interface AnalysisFilters {
  judgment?: Judgment;
  run_id?: number;
}

export type JobStatus = 'pending' | 'done' | 'failed';

export interface Job {
  id: number;
  ticker: string;
  run_id: number;
  status: JobStatus;
  error_message: string | null;
  analysis_id: number | null;
  created_at: string;
}

export interface JobTriggerRequest {
  ticker: string;
  run_id: number;
}

export interface StockPrice {
  ticker: string;
  price_date: string;
  close_price: number;
  fetched_at: string;
}
