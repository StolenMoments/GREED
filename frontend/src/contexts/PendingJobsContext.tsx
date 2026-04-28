import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { useJobPolling } from '../hooks/useJobs';

const STORAGE_KEY = 'greed:pending_jobs';

interface PendingJobsContextValue {
  pendingJobIds: number[];
  addPendingJob: (jobId: number) => void;
  removePendingJob: (jobId: number) => void;
}

const PendingJobsContext = createContext<PendingJobsContextValue | null>(null);

function PendingJobWatcher({
  jobId,
  onCompleted,
}: {
  jobId: number;
  onCompleted: (jobId: number) => void;
}) {
  const query = useJobPolling(jobId);

  useEffect(() => {
    const status = query.data?.status;
    if (status === 'done' || status === 'failed') {
      onCompleted(jobId);
    }
  }, [query.data?.status, jobId, onCompleted]);

  return null;
}

export function PendingJobsProvider({ children }: { children: ReactNode }) {
  const [pendingJobIds, setPendingJobIds] = useState<number[]>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? (JSON.parse(raw) as number[]) : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(pendingJobIds));
  }, [pendingJobIds]);

  const addPendingJob = useCallback((jobId: number) => {
    setPendingJobIds((prev) => (prev.includes(jobId) ? prev : [...prev, jobId]));
  }, []);

  const removePendingJob = useCallback((jobId: number) => {
    setPendingJobIds((prev) => prev.filter((id) => id !== jobId));
  }, []);

  return (
    <PendingJobsContext.Provider value={{ pendingJobIds, addPendingJob, removePendingJob }}>
      {children}
      {pendingJobIds.map((jobId) => (
        <PendingJobWatcher key={jobId} jobId={jobId} onCompleted={removePendingJob} />
      ))}
    </PendingJobsContext.Provider>
  );
}

export function usePendingJobs() {
  const ctx = useContext(PendingJobsContext);
  if (!ctx) {
    throw new Error('usePendingJobs must be used within PendingJobsProvider');
  }
  return ctx;
}
