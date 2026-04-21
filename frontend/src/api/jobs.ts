import { apiClient } from './client';
import type { Job, JobTriggerRequest } from '../types';

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
