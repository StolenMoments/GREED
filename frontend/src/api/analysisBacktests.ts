import { apiClient } from './client';
import type { AnalysisBacktestJob, AnalysisBacktestJobCreate } from '../types';

export async function triggerAnalysisBacktest(
  analysisId: number,
  payload: AnalysisBacktestJobCreate,
): Promise<AnalysisBacktestJob> {
  const response = await apiClient.post<AnalysisBacktestJob>(
    `/analyses/${analysisId}/backtest-jobs`,
    payload,
  );
  return response.data;
}

export async function fetchAnalysisBacktestJobs(
  analysisId: number,
): Promise<AnalysisBacktestJob[]> {
  const response = await apiClient.get<AnalysisBacktestJob[]>(
    `/analyses/${analysisId}/backtest-jobs`,
  );
  return response.data;
}

export async function fetchAnalysisBacktestJob(
  analysisId: number,
  jobId: number,
): Promise<AnalysisBacktestJob> {
  const response = await apiClient.get<AnalysisBacktestJob>(
    `/analyses/${analysisId}/backtest-jobs/${jobId}`,
  );
  return response.data;
}
