import {
  getSignalTone,
  judgmentStyles,
  signalStyles,
} from '../constants/analysisStyles';
import type { AnalysisSummary, EntryCandidate } from '../types';
import { formatDate } from '../utils/formatDate';

const baseTableGrid =
  'xl:grid-cols-[minmax(14rem,1.35fr)_7rem_9rem_minmax(6rem,0.45fr)_5rem]';
const entryGapTableGrid =
  'xl:grid-cols-[minmax(13rem,1.25fr)_7rem_minmax(11rem,0.95fr)_8rem_minmax(6rem,0.45fr)_5rem]';
const priceFormatter = new Intl.NumberFormat('ko-KR');

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
          {showEntryGap ? (
            <div className="space-y-2">
              <div className="h-4 w-20 animate-pulse rounded bg-slate-800/80" />
              <div className="h-3 w-28 animate-pulse rounded bg-slate-800/80" />
            </div>
          ) : null}
          <div className="h-4 w-28 animate-pulse rounded bg-slate-800/80" />
          <div className="h-4 w-24 animate-pulse rounded bg-slate-800/80" />
          <div className="h-4 w-16 animate-pulse rounded bg-slate-800/80" />
        </div>
      ))}
    </div>
  );
}

function formatPrice(price: number | null) {
  return price == null ? null : `${priceFormatter.format(price)}원`;
}

function formatCandidatePrice(candidate: EntryCandidate) {
  const entry = formatPrice(candidate.price);
  const entryMax = formatPrice(candidate.price_max);

  return entryMax ? `${entry}~${entryMax}` : entry;
}

function EntryGapCell({ analysis }: { analysis: AnalysisSummary }) {
  const currentPrice = formatPrice(analysis.current_price);
  const dateLabel = analysis.current_price_date
    ? analysis.current_price_date.slice(5).replace('-', '/')
    : null;
  const candidates = analysis.entry_candidates;

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
                {formatCandidatePrice(candidate)}
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

export function AnalysisTable({
  analyses,
  onSelect,
  showEntryGap = false,
  showRunId = false,
  showSignals = false,
}: {
  analyses: AnalysisSummary[];
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
        {showEntryGap ? <span>entry gap</span> : null}
        <span className="translate-x-1">created</span>
        <span className="text-center">model</span>
        <span className="text-right">action</span>
      </div>
      <div className="divide-y divide-amber-100/10">
        {analyses.map((analysis) => (
          <button
            aria-label={`${analysis.name} (${analysis.ticker}) 분석 상세 보기`}
            className={`grid w-full gap-6 px-5 py-4 text-left transition hover:bg-amber-100/[0.035] focus:outline-none focus-visible:bg-amber-100/[0.05] focus-visible:ring-2 focus-visible:ring-amber-300/70 ${tableGrid} xl:items-center`}
            key={analysis.id}
            onClick={() => onSelect(analysis)}
            type="button"
          >
            <span className="min-w-0">
              <span className="block truncate text-lg font-semibold text-slate-50">
                {analysis.name}
              </span>
              <span className="mt-1 flex flex-wrap items-center gap-2 text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
                <span>{analysis.ticker}</span>
                {showRunId ? (
                  <>
                    <span className="text-slate-700">/</span>
                    <span>run #{analysis.run_id}</span>
                  </>
                ) : null}
              </span>
              {showSignals ? <SignalMeta analysis={analysis} /> : null}
            </span>

            <span
              className={[
                'inline-flex min-w-16 -translate-x-1 justify-center rounded-full border px-3.5 py-1.5 text-sm font-semibold xl:justify-self-center',
                judgmentStyles[analysis.judgment],
              ].join(' ')}
            >
              {analysis.judgment}
            </span>

            {showEntryGap ? <EntryGapCell analysis={analysis} /> : null}

            <span className="translate-x-1 whitespace-nowrap text-sm font-medium text-slate-300">
              {formatDate(analysis.created_at)}
            </span>

            <span className="truncate text-center text-sm font-medium text-slate-400 xl:justify-self-center">
              {analysis.model}
            </span>

            <span className="w-fit rounded-md border border-slate-700/80 px-3 py-2 text-sm font-semibold text-slate-200 transition xl:justify-self-end">
              열기
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
