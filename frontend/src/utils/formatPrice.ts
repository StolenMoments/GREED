const krwFormatter = new Intl.NumberFormat('ko-KR', {
  maximumFractionDigits: 0,
});

const usdFormatter = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function isKoreanTicker(ticker: string): boolean {
  return /^\d+$/.test(ticker.trim());
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
