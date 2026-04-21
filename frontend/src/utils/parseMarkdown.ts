import type { CloudPosition, Judgment, MaAlignment, Trend } from '../types';

export type ParsedField =
  | 'judgment'
  | 'trend'
  | 'cloud_position'
  | 'ma_alignment';

export interface ParsedMarkdown {
  data: {
    judgment?: Judgment;
    trend?: Trend;
    cloud_position?: CloudPosition;
    ma_alignment?: MaAlignment;
    entry_price: number | null;
    target_price: number | null;
    stop_loss: number | null;
  };
  failed: ParsedField[];
  success: boolean;
}

const noneTokens = new Set(['n/a', 'na', '-', '미정', '없음', 'none']);

const fieldPatterns = {
  trend: /추세:\s*(상승|하락|횡보)/,
  cloud_position: /구름대 위치:\s*(구름 위|구름 안|구름 아래)/,
  ma_alignment: /MA 배열:\s*(정배열|역배열|혼조)/,
} as const;

const pricePatterns = {
  entry_price: /^\|\s*진입 조건\s*\|.*?\|\s*([^|\n]+)\|?\s*$/m,
  target_price: /^\|\s*1차 목표\s*\|.*?\|\s*([^|\n]+)\|?\s*$/m,
  stop_loss: /^\|\s*손절 기준\s*\|.*?\|\s*([^|\n]+)\|?\s*$/m,
} as const;

const judgmentBoldPattern = /\*\*(매수|홀드|매도)\*\*/;
const judgmentFallbackPattern =
  /^\s*(?:[-*]\s*)?(?:[[("'`]+)?(매수|홀드|매도)(?:[\])"'`]+)?\s*$/m;

export function parseMarkdown(markdown: string): ParsedMarkdown {
  const failed: ParsedField[] = [];
  const judgment = extractJudgment(markdown);
  const trend = matchField(markdown, fieldPatterns.trend) as Trend | undefined;
  const cloudPosition = matchField(
    markdown,
    fieldPatterns.cloud_position,
  ) as CloudPosition | undefined;
  const maAlignment = matchField(
    markdown,
    fieldPatterns.ma_alignment,
  ) as MaAlignment | undefined;

  if (!judgment) failed.push('judgment');
  if (!trend) failed.push('trend');
  if (!cloudPosition) failed.push('cloud_position');
  if (!maAlignment) failed.push('ma_alignment');

  return {
    data: {
      judgment,
      trend,
      cloud_position: cloudPosition,
      ma_alignment: maAlignment,
      entry_price: parsePrice(markdown, pricePatterns.entry_price),
      target_price: parsePrice(markdown, pricePatterns.target_price),
      stop_loss: parsePrice(markdown, pricePatterns.stop_loss),
    },
    failed,
    success: failed.length === 0,
  };
}

function extractJudgment(markdown: string): Judgment | undefined {
  const boldMatch = judgmentBoldPattern.exec(markdown);
  if (boldMatch) return boldMatch[1] as Judgment;

  const fallbackMatch = judgmentFallbackPattern.exec(markdown);
  return fallbackMatch?.[1] as Judgment | undefined;
}

function matchField(markdown: string, pattern: RegExp): string | undefined {
  return pattern.exec(markdown)?.[1]?.trim();
}

function parsePrice(markdown: string, pattern: RegExp): number | null {
  const rawValue = pattern.exec(markdown)?.[1]?.trim();
  if (!rawValue || noneTokens.has(rawValue.toLocaleLowerCase())) {
    return null;
  }

  const numberMatch = /\d[\d,]*/.exec(rawValue);
  return numberMatch ? Number(numberMatch[0].replaceAll(',', '')) : null;
}
