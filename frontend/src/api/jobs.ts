import { apiClient } from './client';
import type { Job, JobStatus, JobTriggerRequest } from '../types';

export async function triggerAnalysis(
  payload: JobTriggerRequest,
): Promise<Job> {
  const response = await apiClient.post<Job>('/jobs/trigger-analysis', payload);
  return response.data;
}

export async function fetchJob(jobId: number): Promise<Job> {
  const response = await apiClient.get<Job>(`/jobs/${jobId}`);
  return response.data;
}

export async function fetchJobs(
  runId?: number,
  statuses?: JobStatus[],
): Promise<Job[]> {
  const params = new URLSearchParams();
  if (runId !== undefined) {
    params.set('run_id', String(runId));
  }
  statuses?.forEach((status) => params.append('status', status));

  const response = await apiClient.get<Job[]>('/jobs', {
    params,
  });
  return response.data;
}
