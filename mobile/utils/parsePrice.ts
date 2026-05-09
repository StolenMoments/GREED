const noneTokens = new Set(['n/a', 'na', '-', '미정', '없음', 'none']);
const priceValuePattern = /\d[\d,]*(?:\.\d+)?/g;
const entryPricePattern = /^\|\s*[^|\n]*진입[^|\n]*\|.*?\|\s*([^|\n]+)\|?\s*$/gm;
const pricePatterns = {
  target_price: /^\|\s*1차\s*목표[^|]*\|.*?\|\s*([^|\n]+)\|?\s*$/m,
  stop_loss:    /^\|\s*손절 기준\s*\|.*?\|\s*([^|\n]+)\|?\s*$/m,
} as const;

export interface ParsedPrices {
  entry_price:      number | null;
  entry_price_max:  number | null;
  target_price:     number | null;
  target_price_max: number | null;
  stop_loss:        number | null;
  stop_loss_max:    number | null;
}

function parsePriceValues(rawValues: string[]): [number | null, number | null] {
  const values = rawValues.flatMap((raw) => {
    const cleaned = raw.trim();
    if (!cleaned || noneTokens.has(cleaned.toLowerCase())) return [];
    const matches = cleaned.match(priceValuePattern);
    return matches?.map((m) => Number(m.replace(/,/g, ''))) ?? [];
  });
  if (values.length === 0) return [null, null];
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  return [lo, hi !== lo ? hi : null];
}

function parsePriceRange(markdown: string, pattern: RegExp): [number | null, number | null] {
  const raw = pattern.exec(markdown)?.[1]?.trim();
  return parsePriceValues(raw ? [raw] : []);
}

export function parsePricesFromMarkdown(markdown: string): ParsedPrices {
  const entryMatches = Array.from(markdown.matchAll(entryPricePattern), (m) => m[1] ?? '');
  const [entry_price, entry_price_max] = parsePriceValues(entryMatches);
  const [target_price, target_price_max] = parsePriceRange(markdown, pricePatterns.target_price);
  const [stop_loss, stop_loss_max]       = parsePriceRange(markdown, pricePatterns.stop_loss);
  return { entry_price, entry_price_max, target_price, target_price_max, stop_loss, stop_loss_max };
}
