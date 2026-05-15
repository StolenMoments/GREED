import {
  getSignalTone,
  judgmentStyles,
  outcomeStyles,
  signalStyles,
} from '../constants/analysisStyles';
import type {
  AnalysisSummary,
  EntryCandidate,
  EntryCandidateFilter,
} from '../types';
import { formatDate } from '../utils/formatDate';
import { formatPriceByTicker } from '../utils/formatPrice';

const baseTableGrid =
  'xl:grid-cols-[minmax(14rem,1.35fr)_7rem_7rem_9rem_minmax(6rem,0.45fr)_minmax(7.5rem,0.55fr)]';
const entryGapTableGrid =
  'xl:grid-cols-[minmax(13rem,1.2fr)_7rem_6rem_minmax(11rem,0.95fr)_minmax(10rem,0.9fr)_8rem_minmax(7.5rem,0.55fr)]';

function getTableGrid(showEntryGap: boolean) {
  return showEntryGap ? entryGapTableGrid : baseTableGrid;
}

function SignalMeta({ analysis }: { analysis: AnalysisSummary }) {
  return (
    <span className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-medium">
      <span
        className={signalStyles[getSignalTone(analysis.trend, '상승', '하락')]}
      >
        {analysis.trend}
      </span>
      <span className="text-slate-700">/</span>
      <span
        className={
          signalStyles[
            getSignalTone(analysis.cloud_position, '구름 위', '구름 아래')
          ]
        }
      >
        {analysis.cloud_position}
      </span>
      <span className="text-slate-700">/</span>
      <span
        className={
          signalStyles[getSignalTone(analysis.ma_alignment, '정배열', '역배열')]
        }
      >
        {analysis.ma_alignment}
      </span>
    </span>
  );
}

export function AnalysisTableLoading({
  rowCount = 7,
  showEntryGap = false,
}: {
  rowCount?: number;
  showEntryGap?: boolean;
}) {
  const tableGrid = getTableGrid(showEntryGap);

  return (
    <div className="divide-y divide-amber-100/10 overflow-hidden rounded-lg border border-amber-100/10 bg-slate-950/45">
      {Array.from({ length: rowCount }, (_, index) => (
        <div
          className={`grid gap-4 px-5 py-4 ${tableGrid} xl:items-center`}
          key={index}
        >
          <div className="space-y-2">
            <div className="h-4 w-32 animate-pulse rounded bg-slate-700/60" />
            <div className="h-3 w-44 animate-pulse rounded bg-slate-800/80" />
          </div>
          <div className="h-8 w-16 animate-pulse rounded-full bg-slate-800/80" />
          <div className="h-8 w-16 animate-pulse rounded-full bg-slate-800/80" />
          {showEntryGap ? (
            <div className="space-y-2">
              <div className="h-4 w-20 animate-pulse rounded bg-slate-800/80" />
              <div className="h-3 w-28 animate-pulse rounded bg-slate-800/80" />
            </div>
          ) : null}
          {showEntryGap ? (
            <div className="space-y-2">
              <div className="h-4 w-28 animate-pulse rounded bg-slate-800/80" />
              <div className="h-3 w-24 animate-pulse rounded bg-slate-800/80" />
            </div>
          ) : null}
          <div className="h-4 w-28 animate-pulse rounded bg-slate-800/80" />
          {!showEntryGap ? (
            <div className="h-4 w-24 animate-pulse rounded bg-slate-800/80" />
          ) : null}
          <div className="h-4 w-16 animate-pulse rounded bg-slate-800/80" />
        </div>
      ))}
    </div>
  );
}

function formatCandidatePrice(candidate: EntryCandidate, ticker: string) {
  const entry = formatPriceByTicker(candidate.price, ticker);
  const entryMax = formatPriceByTicker(candidate.price_max, ticker);

  return entryMax ? `${entry}~${entryMax}` : entry;
}

function formatPriceRange(
  price: number | null,
  priceMax: number | null,
  ticker: string,
) {
  const formattedPrice = formatPriceByTicker(price, ticker);
  const formattedMax = formatPriceByTicker(priceMax, ticker);

  if (!formattedPrice) {
    return formattedMax ?? '-';
  }

  return formattedMax ? `${formattedPrice}~${formattedMax}` : formattedPrice;
}

function formatSignedPct(price: number, currentPrice: number) {
  const pct = ((price - currentPrice) / currentPrice) * 100;
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;
}

function formatPriceDistancePct(
  price: number | null,
  priceMax: number | null,
  currentPrice: number | null,
) {
  if (currentPrice == null || currentPrice <= 0) {
    return null;
  }

  const formattedPrice = price == null ? null : formatSignedPct(price, currentPrice);
  const formattedMax = priceMax == null ? null : formatSignedPct(priceMax, currentPrice);

  if (!formattedPrice) {
    return formattedMax;
  }

  return formattedMax ? `${formattedPrice}~${formattedMax}` : formattedPrice;
}

function getCandidatePriority(
  candidate: EntryCandidate,
  entryCandidateFilter: EntryCandidateFilter,
) {
  if (entryCandidateFilter === 'pullback') {
    return candidate.label === '눌림' ? 0 : 1;
  }

  if (entryCandidateFilter === 'breakout') {
    return candidate.label === '돌파' ? 0 : 1;
  }

  return 0;
}

function EntryGapCell({
  analysis,
  entryCandidateFilter = 'all',
}: {
  analysis: AnalysisSummary;
  entryCandidateFilter?: EntryCandidateFilter;
}) {
  const currentPrice = formatPriceByTicker(analysis.current_price, analysis.ticker);
  const dateLabel = analysis.current_price_date
    ? analysis.current_price_date.slice(5).replace('-', '/')
    : null;
  const candidates = [...analysis.entry_candidates].sort(
    (a, b) =>
      getCandidatePriority(a, entryCandidateFilter) -
      getCandidatePriority(b, entryCandidateFilter),
  );

  return (
    <span className="min-w-0 space-y-1.5">
      {candidates.length > 0 ? (
        candidates.map((candidate) => {
          const gap =
            candidate.gap_pct == null ? null : `${candidate.gap_pct.toFixed(1)}%`;

          return (
            <span className="grid grid-cols-[2.4rem_minmax(0,1fr)_3.2rem] items-baseline gap-2" key={`${candidate.label}-${candidate.price}`}>
              <span
                className={[
                  'text-xs font-semibold',
                  candidate.is_near ? 'text-amber-200' : 'text-slate-500',
                ].join(' ')}
              >
                {candidate.label}
              </span>
              <span className="truncate text-xs font-medium text-slate-500">
                {formatCandidatePrice(candidate, analysis.ticker)}
              </span>
              <span
                className={[
                  'text-right tabular-nums text-xs font-semibold',
                  candidate.is_near ? 'text-amber-200' : 'text-slate-400',
                ].join(' ')}
              >
                {gap ?? '-'}
              </span>
            </span>
          );
        })
      ) : (
        <span className="block text-xs font-medium text-slate-600">
          진입가 없음
        </span>
      )}
      <span className="block truncate text-xs font-medium text-slate-600">
        {currentPrice ? `현재 ${currentPrice}` : '현재가 없음'}
        {dateLabel ? ` / ${dateLabel}` : ''}
      </span>
    </span>
  );
}

function TargetStopRow({
  label,
  labelClassName,
  pctClassName,
  price,
  priceClassName,
  priceMax,
  ticker,
  currentPrice,
}: {
  label: string;
  labelClassName: string;
  pctClassName: string;
  price: number | null;
  priceClassName: string;
  priceMax: number | null;
  ticker: string;
  currentPrice: number | null;
}) {
  const priceLabel = formatPriceRange(price, priceMax, ticker);
  const pctLabel = formatPriceDistancePct(price, priceMax, currentPrice) ?? '-';

  return (
    <span className="grid grid-cols-[2.4rem_minmax(0,1fr)_4.9rem] items-baseline gap-2">
      <span className={`text-xs font-semibold uppercase tracking-[0.14em] ${labelClassName}`}>
        {label}
      </span>
      <span className={`truncate text-xs tabular-nums ${priceClassName}`}>
        {priceLabel}
      </span>
      <span className={`truncate text-right text-xs font-semibold tabular-nums ${pctClassName}`}>
        {pctLabel}
      </span>
    </span>
  );
}

function TargetStopCell({ analysis }: { analysis: AnalysisSummary }) {
  return (
    <span className="grid min-w-0 gap-1.5">
      <TargetStopRow
        label="TGT"
        labelClassName="text-amber-300/80"
        pctClassName="text-emerald-200/80"
        price={analysis.target_price}
        priceClassName="font-semibold text-amber-100"
        priceMax={analysis.target_price_max}
        ticker={analysis.ticker}
        currentPrice={analysis.current_price}
      />
      <TargetStopRow
        label="STP"
        labelClassName="text-rose-300/70"
        pctClassName="text-rose-200/75"
        price={analysis.stop_loss}
        priceClassName="font-medium text-rose-100/80"
        priceMax={analysis.stop_loss_max}
        ticker={analysis.ticker}
        currentPrice={analysis.current_price}
      />
    </span>
  );
}

export function AnalysisTable({
  analyses,
  entryCandidateFilter = 'all',
  onDelete,
  onSelect,
  showEntryGap = false,
  showRunId = false,
  showSignals = false,
}: {
  analyses: AnalysisSummary[];
  entryCandidateFilter?: EntryCandidateFilter;
  onDelete?: (analysis: AnalysisSummary) => void;
  onSelect: (analysis: AnalysisSummary) => void;
  showEntryGap?: boolean;
  showRunId?: boolean;
  showSignals?: boolean;
}) {
  const tableGrid = getTableGrid(showEntryGap);

  return (
    <div className="overflow-hidden rounded-lg border border-amber-100/10 bg-slate-950/45 shadow-2xl shadow-slate-950/30">
      <div
        className={`hidden ${tableGrid} gap-6 border-b border-amber-100/10 bg-slate-950/80 px-5 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 xl:grid`}
      >
        <span>ticker / name</span>
        <span className="-translate-x-1 text-center">judgment</span>
        <span className="text-center">outcome</span>
        {showEntryGap ? <span>entry gap</span> : null}
        {showEntryGap ? <span>target / stop</span> : null}
        <span className="translate-x-1">created</span>
        {!showEntryGap ? <span className="text-center">model</span> : null}
        <span className="text-right">action</span>
      </div>
      <div className="divide-y divide-amber-100/10">
        {analyses.map((analysis) => (
          <div
            className={`grid w-full gap-6 px-5 py-4 text-left transition hover:bg-amber-100/[0.035] ${tableGrid} xl:items-center`}
            key={analysis.id}
          >
            <button
              aria-label={`${analysis.name} (${analysis.ticker}) 분석 상세 보기`}
              className="min-w-0 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70"
              onClick={() => onSelect(analysis)}
              type="button"
            >
              <span className="block truncate text-lg font-semibold text-slate-50">
                {analysis.name}
              </span>
              <span className="mt-1 block text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
                <span className="flex min-w-0 flex-wrap items-center gap-2">
                  <span>{analysis.ticker}</span>
                  {showRunId ? (
                    <>
                      <span className="text-slate-700">/</span>
                      <span>run #{analysis.run_id}</span>
                    </>
                  ) : null}
                </span>
                {showEntryGap ? (
                  <span className="mt-1 block truncate">{analysis.model}</span>
                ) : null}
              </span>
              {showSignals ? <SignalMeta analysis={analysis} /> : null}
            </button>

            <span
              className={[
                'inline-flex min-w-16 -translate-x-1 justify-center rounded-full border px-3.5 py-1.5 text-sm font-semibold xl:justify-self-center',
                judgmentStyles[analysis.judgment],
              ].join(' ')}
            >
              {analysis.judgment}
            </span>

            <span className="xl:justify-self-center">
              {analysis.outcome ? (
                <span
                  className={[
                    'inline-flex min-w-16 justify-center rounded-full border px-3 py-1.5 text-sm font-semibold',
                    outcomeStyles[analysis.outcome],
                  ].join(' ')}
                >
                  {analysis.outcome}
                </span>
              ) : (
                <span className="text-sm text-slate-700">—</span>
              )}
            </span>

            {showEntryGap ? (
              <EntryGapCell
                analysis={analysis}
                entryCandidateFilter={entryCandidateFilter}
              />
            ) : null}

            {showEntryGap ? <TargetStopCell analysis={analysis} /> : null}

            <span className="translate-x-1 whitespace-nowrap text-sm font-medium text-slate-300">
              {formatDate(analysis.created_at)}
            </span>

            {!showEntryGap ? (
              <span className="truncate text-center text-sm font-medium text-slate-400 xl:justify-self-center">
                {analysis.model}
              </span>
            ) : null}

            <span className="flex flex-wrap justify-start gap-2 xl:justify-self-end">
              <button
                aria-label={`${analysis.name} (${analysis.ticker}) 분석 상세 보기`}
                className="rounded-md border border-slate-700/80 px-3 py-2 text-sm font-semibold text-slate-200 transition hover:bg-slate-800 hover:text-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70"
                onClick={() => onSelect(analysis)}
                type="button"
              >
                열기
              </button>
              {onDelete ? (
                <button
                  aria-label={`${analysis.name} (${analysis.ticker}) 분석 삭제`}
                  className="rounded-md border border-rose-300/25 px-3 py-2 text-sm font-semibold text-rose-100 transition hover:bg-rose-400/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-300/70"
                  onClick={() => onDelete(analysis)}
                  type="button"
                >
                  삭제
                </button>
              ) : null}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
