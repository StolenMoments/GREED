import { apiClient } from './client';
import type { CreateRunPayload, Run } from '../types';

export async function fetchRuns(): Promise<Run[]> {
  const response = await apiClient.get<Run[]>('/runs');
  return response.data;
}

export async function fetchRun(runId: number): Promise<Run> {
  const response = await apiClient.get<Run>(`/runs/${runId}`);
  return response.data;
}

export async function createRun(payload: CreateRunPayload = {}): Promise<Run> {
  const response = await apiClient.post<Run>('/runs', payload);
  return response.data;
}
