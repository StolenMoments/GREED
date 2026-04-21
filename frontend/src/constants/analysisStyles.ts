import type { Judgment } from '../types';

export const judgmentStyles: Record<Judgment, string> = {
  매수: 'border-emerald-300/35 bg-emerald-300/10 text-emerald-100',
  홀드: 'border-amber-300/40 bg-amber-300/10 text-amber-100',
  관망: 'border-slate-400/30 bg-slate-400/10 text-slate-200',
  매도: 'border-rose-300/35 bg-rose-300/10 text-rose-100',
};

export const signalStyles = {
  positive: 'text-emerald-200',
  neutral: 'text-slate-300',
  negative: 'text-rose-200',
} as const;

export function getSignalTone(
  value: string,
  positive: string,
  negative: string,
): keyof typeof signalStyles {
  if (value === positive) return 'positive';
  if (value === negative) return 'negative';
  return 'neutral';
}
