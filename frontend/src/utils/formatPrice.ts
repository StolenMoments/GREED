const krwFormatter = new Intl.NumberFormat('ko-KR', {
  maximumFractionDigits: 0,
});

const usdFormatter = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function isKoreanTicker(ticker: string): boolean {
  const normalized = ticker.trim().toUpperCase();
  return /^[A-Z0-9]{6}$/.test(normalized) && /\d/.test(normalized);
}

export function formatPriceByTicker(
  price: number | null | undefined,
  ticker: string,
): string | null {
  if (price == null) {
    return null;
  }

  if (isKoreanTicker(ticker)) {
    return `${krwFormatter.format(price)}원`;
  }

  return `$${usdFormatter.format(price)}`;
}
