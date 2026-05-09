export function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = Date.now();
  const diff = now - date.getTime();

  const minutes = Math.floor(diff / 60_000);
  const hours   = Math.floor(diff / 3_600_000);
  const days    = Math.floor(diff / 86_400_000);

  if (minutes < 1)  return '방금 전';
  if (minutes < 60) return `${minutes}분 전`;
  if (hours < 24)   return `${hours}시간 전`;
  if (days < 7)     return `${days}일 전`;
  return date.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' });
}
