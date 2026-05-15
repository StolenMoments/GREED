import { useQuery } from '@tanstack/react-query';
import { fetchHealth } from '../api/health';

export const healthKeys = {
  all: ['health'] as const,
};

export function useDbHealth() {
  return useQuery({
    queryKey: healthKeys.all,
    queryFn: fetchHealth,
    refetchInterval: 5000,
    retry: false,
  });
}
