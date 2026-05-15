import { apiClient } from './client';

export type DatabaseHealthStatus = 'up' | 'down';

export interface HealthStatus {
  api: 'ok';
  database: {
    status: DatabaseHealthStatus;
    checked_at: string;
  };
}

export async function fetchHealth(): Promise<HealthStatus> {
  const response = await apiClient.get<HealthStatus>('/health');
  return response.data;
}
