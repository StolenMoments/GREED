import { apiClient } from './client';
import type { Candidate, CandidateScanJob, ScanSummaryItem } from '../types';

export async function triggerScan(
  analysisId: number,
  payload: { threshold: number },
): Promise<CandidateScanJob> {
  const response = await apiClient.post<CandidateScanJob>(
    `/candidates/scan/${analysisId}`,
    payload,
  );
  return response.data;
}

export async function fetchScanJob(
  analysisId: number,
  jobId: number,
): Promise<CandidateScanJob> {
  const response = await apiClient.get<CandidateScanJob>(
    `/candidates/scan-jobs/${analysisId}/${jobId}`,
  );
  return response.data;
}

export async function fetchLatestScanJob(
  analysisId: number,
): Promise<CandidateScanJob | null> {
  const response = await apiClient.get<CandidateScanJob[]>(
    `/candidates/scan-jobs/${analysisId}`,
  );
  return response.data[0] ?? null;
}

export async function fetchCandidates(
  analysisId: number,
  minScore: number,
): Promise<Candidate[]> {
  const response = await apiClient.get<Candidate[]>('/candidates', {
    params: { analysis_id: analysisId, min_score: minScore },
  });
  return response.data;
}

export async function fetchScanSummary(): Promise<ScanSummaryItem[]> {
  const response = await apiClient.get<ScanSummaryItem[]>('/candidates/scan-summary');
  return response.data;
}
