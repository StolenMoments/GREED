import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { healthKeys, useDbHealth } from '../hooks/useDbHealth';

function formatCheckedAt(value: string | undefined): string {
  if (!value) {
    return '';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '';
  }

  return date.toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function DatabaseStatusBanner() {
  const queryClient = useQueryClient();
  const healthQuery = useDbHealth();
  const status = healthQuery.data?.database.status;
  const previousStatusRef = useRef<typeof status>(undefined);
  const [showRecovered, setShowRecovered] = useState(false);

  useEffect(() => {
    const previousStatus = previousStatusRef.current;

    if (previousStatus === 'down' && status === 'up') {
      setShowRecovered(true);
      queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] !== healthKeys.all[0],
      });

      const timer = window.setTimeout(() => setShowRecovered(false), 5000);
      previousStatusRef.current = status;
      return () => window.clearTimeout(timer);
    }

    previousStatusRef.current = status;
    return undefined;
  }, [queryClient, status]);

  if (healthQuery.isError) {
    return (
      <div className="rounded-lg border border-rose-300/30 bg-rose-950/50 px-4 py-3 text-sm text-rose-100">
        API 연결을 확인하지 못했습니다. 백엔드 서버와 터널 상태를 확인하세요.
      </div>
    );
  }

  if (status === 'down') {
    const checkedAt = formatCheckedAt(healthQuery.data?.database.checked_at);
    return (
      <div className="rounded-lg border border-amber-300/40 bg-amber-950/50 px-4 py-3 text-sm text-amber-100">
        DB 연결이 끊겼습니다. 터널 복구를 기다리는 중입니다.
        {checkedAt ? <span className="ml-2 text-amber-200/70">마지막 확인 {checkedAt}</span> : null}
      </div>
    );
  }

  if (showRecovered) {
    return (
      <div className="rounded-lg border border-emerald-300/30 bg-emerald-950/40 px-4 py-3 text-sm text-emerald-100">
        DB 연결이 복구되었습니다. 화면 데이터를 다시 불러옵니다.
      </div>
    );
  }

  return null;
}
