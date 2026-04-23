import type { StockPrice } from '../types';
import { formatPriceByTicker } from '../utils/formatPrice';

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
  ticker: string;
  currentPrice?: StockPrice;
  entryPrice?: number | null;
  entryPriceMax?: number | null;
  isRefreshing?: boolean;
  onRefresh?: () => void;
  refreshError?: boolean;
  targetPrice?: number | null;
  targetPriceMax?: number | null;
  stopLoss?: number | null;
  stopLossMax?: number | null;
}

function PriceLevels({
  ticker,
  currentPrice,
  entryPrice,
  entryPriceMax,
  isRefreshing = false,
  onRefresh,
  refreshError = false,
  targetPrice,
  targetPriceMax,
  stopLoss,
  stopLossMax,
}: PriceLevelsProps) {
  const current = currentPrice?.close_price;
  const priceTicker = currentPrice?.ticker ?? ticker;

  return (
    <aside className="rounded-lg border border-amber-100/10 bg-slate-950/55 p-6">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-base font-semibold text-slate-100">가격 레벨</h3>
        <div className="flex items-center gap-2">
          {currentPrice && (
            <span className="text-xs font-medium text-slate-500">
              {currentPrice.price_date.slice(5).replace('-', '/')}
            </span>
          )}
          {onRefresh ? (
            <button
              className="rounded-md border border-amber-200/20 px-2.5 py-1 text-xs font-semibold text-amber-100 transition hover:bg-amber-100/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70 disabled:cursor-not-allowed disabled:border-slate-800 disabled:text-slate-600 disabled:hover:bg-transparent"
              disabled={isRefreshing}
              onClick={onRefresh}
              type="button"
            >
              {isRefreshing ? '갱신 중' : '갱신'}
            </button>
          ) : null}
        </div>
      </div>

      <div className="mt-5">
        <p className="tabular-nums text-4xl font-semibold tracking-tight text-amber-100">
          {formatPriceByTicker(current, priceTicker) ?? '—'}
        </p>
        <p className="mt-1 text-xs font-medium uppercase tracking-[0.2em] text-slate-600">
          현재가
        </p>
      </div>

      {refreshError ? (
        <p className="mt-3 rounded-md border border-rose-300/20 bg-rose-950/20 px-3 py-2 text-xs font-medium text-rose-100">
          현재가를 갱신하지 못했습니다.
        </p>
      ) : null}

      <div className="mt-6 space-y-4 border-t border-slate-800/70 pt-5">
        <PriceRow label="목표가" price={targetPrice} priceMax={targetPriceMax} current={current} ticker={priceTicker} tone="target" />
        <PriceRow label="진입가" price={entryPrice} priceMax={entryPriceMax} current={current} ticker={priceTicker} tone="entry" />
        <PriceRow label="손절가" price={stopLoss} priceMax={stopLossMax} current={current} ticker={priceTicker} tone="stop" />
      </div>
    </aside>
  );
}

function PriceRow({
  current,
  label,
  price,
  priceMax,
  ticker,
  tone,
}: {
  current?: number;
  label: string;
  price?: number | null;
  priceMax?: number | null;
  ticker: string;
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
          {formatPriceByTicker(price, ticker)}
          <span className="mx-1.5 font-normal text-slate-500">~</span>
          {formatPriceByTicker(priceMax, ticker)}
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
        {formatPriceByTicker(price, ticker) ?? '—'}
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
