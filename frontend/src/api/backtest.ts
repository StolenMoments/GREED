import { apiClient } from './client';

export interface BacktestStat {
  horizon: number;
  score_bucket: string;
  count: number;
  censored_count: number;
  win_rate: number | null;
  mean: number | null;
  median: number | null;
  std: number | null;
  p25: number | null;
  p75: number | null;
  min: number | null;
  max: number | null;
}

export interface BacktestRunSummary {
  id: number;
  created_at: string;
  universe: string;
  buy_threshold: number;
  horizons: string;
  warmup_weeks: number;
  data_start: string | null;
  data_end: string | null;
  ticker_count: number;
  signal_count: number;
  source_analysis_id: number | null;
  strategy_kind: string | null;
  similarity_threshold: number | null;
  notes: string | null;
  source_ticker: string | null;
  source_name: string | null;
}

export interface BacktestEventSummary {
  signal_count: number;
  entered_count: number;
  no_entry_count: number;
  target_count: number;
  stop_count: number;
  open_count: number;
  expiry_count: number;
  target_hit_rate: number | null;
  positive_return_rate: number | null;
  win_rate: number | null;
  mean_return: number | null;
  expectancy: number | null;
  median_return: number | null;
  avg_days_held: number | null;
  planned_target_return: number | null;
  planned_stop_return: number | null;
  planned_risk_reward_ratio: number | null;
  avg_gain_return: number | null;
  avg_loss_return: number | null;
  realized_payoff_ratio: number | null;
}

export type BacktestStrategyKind = 'ichimoku_span2_breakout' | 'daily_20d_40pct_rally';

export interface BacktestStrategyJob {
  id: number;
  strategy_kind: BacktestStrategyKind;
  status: 'pending' | 'running' | 'done' | 'failed';
  backtest_run_id: number | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface DailyRallyRuleStat {
  id: number;
  run_id: number;
  rule_key: string;
  rule_label: string;
  support: number;
  positives: number;
  total_matches: number;
  precision: number;
  base_rate: number;
  lift: number;
  score: number;
}

export interface DailyRallyInsights {
  run_id: number;
  rule_count: number;
  rules: DailyRallyRuleStat[];
}

export interface DailyRallyReturnStat {
  horizon: number;
  count: number;
  censored_count: number;
  win_rate: number | null;
  mean: number | null;
  median: number | null;
  std: number | null;
  p25: number | null;
  p75: number | null;
  min: number | null;
  max: number | null;
}

export interface DailyRallyPatternStat {
  id: number;
  run_id: number;
  pattern_key: string;
  pattern_label: string;
  support: number;
  positives: number;
  total_matches: number;
  precision: number;
  base_rate: number;
  lift: number;
  score: number;
  return_stats: DailyRallyReturnStat[];
}

export interface DailyRallyPatternStats {
  run_id: number;
  pattern_count: number;
  patterns: DailyRallyPatternStat[];
}

export interface DailyRallyCandidate {
  id: number;
  run_id: number;
  ticker: string;
  name: string;
  signal_date: string;
  close_price: number;
  matched_rules: string[];
  matched_rule_count: number;
  max_rule_score: number | null;
  mean_rule_score: number | null;
  features: Record<string, boolean | number | string | null>;
}

export interface DailyRallyCandidates {
  run_id: number;
  candidate_count: number;
  candidates: DailyRallyCandidate[];
}

export interface DailyRallyYearValidation {
  year: number;
  total: number;
  positives: number;
  base_rate: number;
  positive_forward_return_120d_mean: number | null;
  censored_120d_count: number;
  partial: boolean;
}

export interface DailyRallyTickerConcentration {
  ticker: string;
  name: string;
  total_count: number;
  positive_count: number;
  positive_share: number;
}

export type DailyRallyValidationClassification = 'stable' | 'fragile' | 'insufficient';

export interface DailyRallyPatternStability {
  pattern_key: string;
  pattern_label: string;
  total_matches: number;
  positives: number;
  full_period_lift: number;
  test_window_count: number;
  median_train_lift: number | null;
  median_test_lift: number | null;
  test_lift_gt_1_ratio: number | null;
  classification: DailyRallyValidationClassification;
}

export interface DailyRallyWalkForwardWindow {
  train_years: number[];
  test_year: number;
  pattern_key: string | null;
  pattern_label: string | null;
  train_support: number;
  train_total_matches: number;
  train_precision: number | null;
  train_base_rate: number | null;
  train_lift: number | null;
  test_matches: number;
  test_positives: number;
  test_precision: number | null;
  test_base_rate: number | null;
  test_lift: number | null;
  classification: DailyRallyValidationClassification;
}

export interface DailyRallyValidation {
  run_id: number;
  summary: Record<string, unknown>;
  year_breakdown: DailyRallyYearValidation[];
  ticker_concentration: DailyRallyTickerConcentration[];
  pattern_stability: DailyRallyPatternStability[];
  walk_forward_windows: DailyRallyWalkForwardWindow[];
  warnings: string[];
}

export interface ContractBreakdownItem {
  signal_count: number;
  entered_count: number;
  no_entry_count: number;
  target_count: number;
  stop_count: number;
  expiry_count: number;
  target_hit_rate: number | null;
  positive_return_rate: number | null;
  mean_return: number | null;
  median_return: number | null;
  avg_days_held: number | null;
}

export interface ContractTickerBreakdownItem extends ContractBreakdownItem {
  ticker: string;
  name: string;
}

export interface ContractBreakdown {
  focus_threshold: number;
  focus: ContractBreakdownItem;
  by_score: Record<string, ContractBreakdownItem>;
  by_year: Record<string, ContractBreakdownItem>;
  top_tickers: ContractTickerBreakdownItem[];
  bottom_tickers: ContractTickerBreakdownItem[];
}

export interface BacktestRunDetail extends BacktestRunSummary {
  stats: BacktestStat[];
  event_summary: BacktestEventSummary | null;
  contract_breakdown: ContractBreakdown | null;
}

export interface BacktestUniverseMember {
  ticker: string;
  name: string;
  market: string;
  active: boolean;
  sort_order: number;
  source: string;
  created_at: string;
  updated_at: string;
}

export interface BacktestUniverseCreatePayload {
  ticker: string;
  name: string;
  sort_order?: number;
}

export interface BacktestUniverseUpdatePayload {
  name?: string;
  active?: boolean;
  sort_order?: number;
}

export async function fetchBacktestRuns(): Promise<BacktestRunSummary[]> {
  const response = await apiClient.get<BacktestRunSummary[]>('/backtest/runs');
  return response.data;
}

export async function fetchBacktestRun(id: number): Promise<BacktestRunDetail> {
  const response = await apiClient.get<BacktestRunDetail>(`/backtest/runs/${id}`);
  return response.data;
}

export async function createBacktestStrategyJob(
  strategyKind: BacktestStrategyKind,
): Promise<BacktestStrategyJob> {
  const response = await apiClient.post<BacktestStrategyJob>('/backtest/strategy-jobs', {
    strategy_kind: strategyKind,
  });
  return response.data;
}

export async function fetchBacktestStrategyJobs(): Promise<BacktestStrategyJob[]> {
  const response = await apiClient.get<BacktestStrategyJob[]>('/backtest/strategy-jobs');
  return response.data;
}

export async function fetchDailyRallyInsights(runId: number): Promise<DailyRallyInsights> {
  const response = await apiClient.get<DailyRallyInsights>(
    `/backtest/runs/${runId}/daily-rally-insights`,
  );
  return response.data;
}

export async function fetchDailyRallyPatternStats(runId: number): Promise<DailyRallyPatternStats> {
  const response = await apiClient.get<DailyRallyPatternStats>(
    `/backtest/runs/${runId}/daily-rally-pattern-stats`,
  );
  return response.data;
}

export async function fetchDailyRallyCandidates(runId: number): Promise<DailyRallyCandidates> {
  const response = await apiClient.get<DailyRallyCandidates>(
    `/backtest/runs/${runId}/daily-rally-candidates`,
  );
  return response.data;
}

export async function fetchDailyRallyValidation(runId: number): Promise<DailyRallyValidation> {
  const response = await apiClient.get<DailyRallyValidation>(
    `/backtest/runs/${runId}/daily-rally-validation`,
  );
  return response.data;
}

export async function fetchBacktestUniverse(
  includeInactive = true,
): Promise<BacktestUniverseMember[]> {
  const response = await apiClient.get<BacktestUniverseMember[]>('/backtest/universe', {
    params: { include_inactive: includeInactive },
  });
  return response.data;
}

export async function createBacktestUniverseMember(
  payload: BacktestUniverseCreatePayload,
): Promise<BacktestUniverseMember> {
  const response = await apiClient.post<BacktestUniverseMember>('/backtest/universe', payload);
  return response.data;
}

export async function updateBacktestUniverseMember(
  ticker: string,
  payload: BacktestUniverseUpdatePayload,
): Promise<BacktestUniverseMember> {
  const response = await apiClient.patch<BacktestUniverseMember>(
    `/backtest/universe/${ticker}`,
    payload,
  );
  return response.data;
}

export async function deactivateBacktestUniverseMember(ticker: string): Promise<void> {
  await apiClient.delete(`/backtest/universe/${ticker}`);
}
