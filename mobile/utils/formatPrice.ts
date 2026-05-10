export function formatPrice(price: number | null, priceMax: number | null): string | null {
  if (price == null) return null;
  const fmt = (n: number) => n.toLocaleString('ko-KR');
  return priceMax != null ? `${fmt(price)}~${fmt(priceMax)}` : fmt(price);
}
