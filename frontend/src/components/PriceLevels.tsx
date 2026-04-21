import type { StockPrice } from '../types';

const priceFormatter = new Intl.NumberFormat('ko-KR');

function calcPct(price: number, current: number): string {
  const pct = ((price - current) / current) * 100;
  return (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
}

const toneStyles = {
  target: 'text-emerald-300',
  entry: 'text-amber-300/70',
  stop: 'text-rose-300',
} as const;

interface PriceLevelsProps {
  currentPrice?: StockPrice;
  entryPrice?: number | null;
  entryPriceMax?: number | null;
  targetPrice?: number | null;
  targetPriceMax?: number | null;
  stopLoss?: number | null;
  stopLossMax?: number | null;
}

function PriceLevels({
  currentPrice,
  entryPrice,
  entryPriceMax,
  targetPrice,
  targetPriceMax,
  stopLoss,
  stopLossMax,
}: PriceLevelsProps) {
  const current = currentPrice?.close_price;

  return (
    <aside className="rounded-lg border border-amber-100/10 bg-slate-950/55 p-6">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-base font-semibold text-slate-100">가격 레벨</h3>
        {currentPrice && (
          <span className="text-xs font-medium text-slate-500">
            {currentPrice.price_date.slice(5).replace('-', '/')}
          </span>
        )}
      </div>

      <div className="mt-5">
        <p className="tabular-nums text-4xl font-semibold tracking-tight text-amber-100">
          {current !== undefined ? `${priceFormatter.format(current)}원` : '—'}
        </p>
        <p className="mt-1 text-xs font-medium uppercase tracking-[0.2em] text-slate-600">
          현재가
        </p>
      </div>

      <div className="mt-6 space-y-4 border-t border-slate-800/70 pt-5">
        <PriceRow label="목표가" price={targetPrice} priceMax={targetPriceMax} current={current} tone="target" />
        <PriceRow label="진입가" price={entryPrice} priceMax={entryPriceMax} current={current} tone="entry" />
        <PriceRow label="손절가" price={stopLoss} priceMax={stopLossMax} current={current} tone="stop" />
      </div>
    </aside>
  );
}

function PriceRow({
  current,
  label,
  price,
  priceMax,
  tone,
}: {
  current?: number;
  label: string;
  price?: number | null;
  priceMax?: number | null;
  tone: keyof typeof toneStyles;
}) {
  const colorClass = toneStyles[tone];
  const isRange = price != null && priceMax != null;
  const pct =
    price != null && current !== undefined && !isRange ? calcPct(price, current) : null;

  if (isRange) {
    return (
      <div className="grid grid-cols-[auto_1fr] items-baseline gap-x-3">
        <span className={`text-sm font-medium ${colorClass}`}>{label}</span>
        <span className={`text-right tabular-nums text-lg font-medium ${colorClass}`}>
          {priceFormatter.format(price)}
          <span className="mx-1.5 font-normal text-slate-500">~</span>
          {priceFormatter.format(priceMax)}원
        </span>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-[auto_1fr_auto] items-baseline gap-x-3">
      <span className={`text-sm font-medium ${colorClass}`}>{label}</span>
      <span
        className={`text-right tabular-nums text-lg font-semibold ${price != null ? colorClass : 'text-slate-600'}`}
      >
        {price != null ? `${priceFormatter.format(price)}원` : '—'}
      </span>
      <span
        className={`tabular-nums text-sm font-medium ${pct !== null ? colorClass : 'text-slate-700'}`}
      >
        {pct ?? '—'}
      </span>
    </div>
  );
}

export default PriceLevels;
