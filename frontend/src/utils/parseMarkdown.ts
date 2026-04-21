import type { CloudPosition, Judgment, MaAlignment, Trend } from '../types';

export type ParsedField =
  | 'judgment'
  | 'trend'
  | 'cloud_position'
  | 'ma_alignment';

type PriceData = {
  entry_price: number | null;
  entry_price_max: number | null;
  target_price: number | null;
  target_price_max: number | null;
  stop_loss: number | null;
  stop_loss_max: number | null;
};

type RequiredData = PriceData & {
  judgment: Judgment;
  trend: Trend;
  cloud_position: CloudPosition;
  ma_alignment: MaAlignment;
};

type PartialData = PriceData & {
  judgment?: Judgment;
  trend?: Trend;
  cloud_position?: CloudPosition;
  ma_alignment?: MaAlignment;
};

export type ParsedMarkdown =
  | { success: true; data: RequiredData; failed: [] }
  | { success: false; data: PartialData; failed: [ParsedField, ...ParsedField[]] };

const noneTokens = new Set(['n/a', 'na', '-', '미정', '없음', 'none']);

const fieldPatterns = {
  trend: /\*{0,2}추세\*{0,2}\s*:\s*(상승|하락|횡보)/,
  cloud_position: /\*{0,2}구름대 위치\*{0,2}\s*:\s*(구름 위|구름 안|구름 아래)/,
  ma_alignment: /\*{0,2}MA 배열\*{0,2}\s*:\s*(정배열|역배열|혼조)/,
} as const;

const pricePatterns = {
  entry_price: /^\|[^|]*진입\s*조건[^|]*\|.*?\|\s*([^|\n]+)\|?\s*$/m,
  target_price: /^\|\s*1차\s*목표[^|]*\|.*?\|\s*([^|\n]+)\|?\s*$/m,
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

  const [entry_price, entry_price_max] = parsePriceRange(markdown, pricePatterns.entry_price);
  const [target_price, target_price_max] = parsePriceRange(markdown, pricePatterns.target_price);
  const [stop_loss, stop_loss_max] = parsePriceRange(markdown, pricePatterns.stop_loss);
  const priceData: PriceData = {
    entry_price,
    entry_price_max,
    target_price,
    target_price_max,
    stop_loss,
    stop_loss_max,
  };

  if (failed.length === 0) {
    return {
      success: true,
      data: {
        ...priceData,
        judgment: judgment as Judgment,
        trend: trend as Trend,
        cloud_position: cloudPosition as CloudPosition,
        ma_alignment: maAlignment as MaAlignment,
      },
      failed: [],
    };
  }

  return {
    success: false,
    data: { ...priceData, judgment, trend, cloud_position: cloudPosition, ma_alignment: maAlignment },
    failed: failed as [ParsedField, ...ParsedField[]],
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

function parsePriceRange(markdown: string, pattern: RegExp): [number | null, number | null] {
  const rawValue = pattern.exec(markdown)?.[1]?.trim();
  if (!rawValue || noneTokens.has(rawValue.toLocaleLowerCase())) {
    return [null, null];
  }

  const matches = rawValue.match(/\d[\d,]*/g);
  if (!matches) return [null, null];

  const values = matches.map((m) => Number(m.replaceAll(',', '')));
  if (values.length === 1) return [values[0], null];

  const lo = Math.min(values[0], values[1]);
  const hi = Math.max(values[0], values[1]);
  return [lo, hi !== lo ? hi : null];
}
