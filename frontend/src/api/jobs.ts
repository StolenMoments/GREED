import { apiClient } from './client';
import type {
  Job,
  JobOverview,
  JobOverviewStatus,
  JobStatus,
  JobTriggerRequest,
} from '../types';

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

export async function fetchJobOverview(
  statuses?: JobOverviewStatus[],
): Promise<JobOverview[]> {
  const params = new URLSearchParams();
  statuses?.forEach((status) => params.append('status', status));

  const response = await apiClient.get<JobOverview[]>('/jobs/overview', {
    params,
  });
  return response.data;
}
