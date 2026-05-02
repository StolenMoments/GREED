import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStockSummary } from '../hooks/useStocks';
import type { StockSummary } from '../types';

const PAGE_SIZE = 25;
const KOREAN_INITIALS = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ';

type SortKey = 'name' | 'buy_count' | 'hold_count' | 'sell_count' | 'latest_at';

const DEFAULT_SORT_DIR: Record<SortKey, 'asc' | 'desc'> = {
  name: 'asc',
  buy_count: 'desc',
  hold_count: 'desc',
  sell_count: 'desc',
  latest_at: 'desc',
};

function getVisiblePages(page: number, totalPages: number) {
  const end = Math.min(totalPages, Math.max(page + 2, 5));
  const start = Math.max(1, Math.min(page - 2, end - 4));
  return Array.from({ length: end - start + 1 }, (_, index) => start + index);
}

function formatShortDate(value: string) {
  const d = new Date(value);
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
  })
    .format(d)
    .replace(/\.\s*/g, '.')
    .replace(/\.$/, '');
}

function isKoreanInitialQuery(value: string) {
  return Boolean(value) && [...value].every((char) => KOREAN_INITIALS.includes(char));
}

const COL = 'grid-cols-[1fr_4.5rem_4.5rem_4.5rem_8rem]';

interface PaginationControlsProps {
  disabled: boolean;
  onPageChange: (page: number) => void;
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

function PaginationControls({
  disabled,
  onPageChange,
  page,
  pageSize,
  total,
  totalPages,
}: PaginationControlsProps) {
  const firstItem = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const lastItem = Math.min(page * pageSize, total);
  const pages = getVisiblePages(page, totalPages);
  const isFirstPage = page <= 1;
  const isLastPage = totalPages === 0 || page >= totalPages;
  const buttonBase =
    'h-9 rounded-md border px-3 text-sm font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70 disabled:cursor-not-allowed disabled:border-slate-800 disabled:text-slate-700 disabled:hover:bg-transparent';

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.06] pt-4">
      <p className="text-sm font-medium text-slate-400">
        <span className="text-slate-200">
          {firstItem.toLocaleString('ko-KR')}-{lastItem.toLocaleString('ko-KR')}
        </span>{' '}
        / 총 {total.toLocaleString('ko-KR')}개
      </p>

      {totalPages > 1 ? (
        <nav
          aria-label="종목 목록 페이지"
          className="flex flex-wrap items-center gap-1.5"
        >
          <button
            className={`${buttonBase} border-slate-700/80 text-slate-300 hover:bg-slate-800 hover:text-slate-50`}
            disabled={disabled || isFirstPage}
            onClick={() => onPageChange(1)}
            type="button"
          >
            처음
          </button>
          <button
            className={`${buttonBase} border-slate-700/80 text-slate-300 hover:bg-slate-800 hover:text-slate-50`}
            disabled={disabled || isFirstPage}
            onClick={() => onPageChange(page - 1)}
            type="button"
          >
            이전
          </button>

          {pages.map((pageNumber) => {
            const isActive = pageNumber === page;
            return (
              <button
                aria-current={isActive ? 'page' : undefined}
                className={[
                  buttonBase,
                  isActive
                    ? 'border-amber-300 bg-amber-300 text-slate-950'
                    : 'border-slate-700/80 text-slate-300 hover:bg-slate-800 hover:text-slate-50',
                ].join(' ')}
                disabled={disabled || isActive}
                key={pageNumber}
                onClick={() => onPageChange(pageNumber)}
                type="button"
              >
                {pageNumber}
              </button>
            );
          })}

          <button
            className={`${buttonBase} border-slate-700/80 text-slate-300 hover:bg-slate-800 hover:text-slate-50`}
            disabled={disabled || isLastPage}
            onClick={() => onPageChange(page + 1)}
            type="button"
          >
            다음
          </button>
          <button
            className={`${buttonBase} border-slate-700/80 text-slate-300 hover:bg-slate-800 hover:text-slate-50`}
            disabled={disabled || isLastPage}
            onClick={() => onPageChange(totalPages)}
            type="button"
          >
            끝
          </button>
        </nav>
      ) : null}
    </div>
  );
}

function SortIcon({ active, dir }: { active: boolean; dir: 'asc' | 'desc' }) {
  if (!active)
    return (
      <span className="ml-1 opacity-0 transition-opacity group-hover/hdr:opacity-100">
        ⇅
      </span>
    );
  return (
    <span className="ml-1 text-amber-300">{dir === 'asc' ? '▲' : '▼'}</span>
  );
}

function LoadingRows() {
  return (
    <div className="overflow-hidden rounded-xl border border-white/[0.06] bg-slate-950/60">
      <div className={`grid ${COL} border-b border-white/[0.06] px-6 py-3`}>
        {['종목', '매수', '홀드', '매도', '분석일'].map((label, i) => (
          <div
            key={label}
            className={`h-3 w-8 animate-pulse rounded bg-slate-800 ${i > 0 ? 'justify-self-center' : ''} ${i === 4 ? 'justify-self-end' : ''}`}
          />
        ))}
      </div>
      {Array.from({ length: 7 }, (_, i) => (
        <div
          className={`grid ${COL} items-center border-b border-white/[0.04] px-6 py-4 last:border-0`}
          key={i}
        >
          <div className="space-y-2">
            <div
              className="h-3.5 animate-pulse rounded bg-slate-800"
              style={{ width: `${80 + (i * 23) % 80}px` }}
            />
            <div className="h-2.5 w-16 animate-pulse rounded bg-slate-800/60" />
          </div>
          {[0, 1, 2].map((j) => (
            <div
              key={j}
              className="h-3.5 w-5 animate-pulse justify-self-center rounded bg-slate-800/60"
            />
          ))}
          <div className="h-3 w-14 animate-pulse justify-self-end rounded bg-slate-800/40" />
        </div>
      ))}
    </div>
  );
}

function JudgmentCount({
  count,
  variant,
}: {
  count: number;
  variant: 'buy' | 'hold' | 'sell';
}) {
  const activeColor = {
    buy: 'text-[oklch(0.75_0.14_152)]',
    hold: 'text-[oklch(0.82_0.16_80)]',
    sell: 'text-[oklch(0.68_0.18_25)]',
  }[variant];

  return (
    <span
      className={`tabular-nums text-lg font-semibold leading-none transition-opacity ${
        count === 0 ? 'text-slate-700' : activeColor
      }`}
    >
      {count}
    </span>
  );
}

function StockRow({ stock }: { stock: StockSummary }) {
  const navigate = useNavigate();

  return (
    <button
      className={`group grid w-full ${COL} items-center border-b border-white/[0.04] px-6 py-4 text-left last:border-0 hover:bg-amber-300/[0.035] focus:outline-none focus-visible:bg-amber-300/[0.05] focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-amber-300/40`}
      onClick={() => navigate(`/analyses?q=${stock.ticker}`)}
      type="button"
    >
      <span className="min-w-0">
        <span className="block truncate text-lg font-semibold leading-snug text-slate-50 group-hover:text-white">
          {stock.name}
        </span>
        <span className="mt-1 block text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
          {stock.ticker}
        </span>
      </span>

      <span className="flex justify-center">
        <JudgmentCount count={stock.buy_count} variant="buy" />
      </span>
      <span className="flex justify-center">
        <JudgmentCount count={stock.hold_count} variant="hold" />
      </span>
      <span className="flex justify-center">
        <JudgmentCount count={stock.sell_count} variant="sell" />
      </span>

      <span className="justify-self-end text-sm tabular-nums font-medium text-slate-50 group-hover:text-white">
        {formatShortDate(stock.latest_at)}
      </span>
    </button>
  );
}

function EmptyState() {
  const navigate = useNavigate();
  return (
    <div className="rounded-xl border border-white/[0.06] bg-slate-950/60 px-8 py-14 text-center">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-600">
        종목 없음
      </p>
      <p className="mt-3 text-sm leading-relaxed text-slate-400">
        Runs에서 종목을 분석하면
        <br />
        판정 이력이 여기에 집계됩니다.
      </p>
      <button
        className="mt-6 rounded-lg border border-amber-300/20 px-5 py-2 text-sm font-medium text-amber-300/80 transition hover:border-amber-300/40 hover:text-amber-300"
        onClick={() => navigate('/runs')}
        type="button"
      >
        Runs 바로가기
      </button>
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-xl border border-rose-400/10 bg-rose-950/20 px-6 py-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-rose-200">
            종목 목록을 불러오지 못했습니다.
          </p>
          <p className="mt-1 text-xs text-rose-200/50">
            백엔드 응답 상태를 확인한 뒤 다시 시도하세요.
          </p>
        </div>
        <button
          className="shrink-0 rounded-lg border border-rose-300/20 px-4 py-2 text-sm font-medium text-rose-300/70 transition hover:border-rose-300/40 hover:text-rose-300"
          onClick={onRetry}
          type="button"
        >
          다시 시도
        </button>
      </div>
    </div>
  );
}

const SORT_COLUMNS = [
  { key: 'buy_count' as SortKey,  label: '매수', align: 'justify-center' },
  { key: 'hold_count' as SortKey, label: '홀드', align: 'justify-center' },
  { key: 'sell_count' as SortKey, label: '매도', align: 'justify-center' },
  { key: 'latest_at' as SortKey,  label: '분석일', align: 'justify-end' },
];

function StockSummaryPage() {
  const { data: stocks = [], isError, isLoading, refetch } = useStockSummary();

  const [queryInput, setQueryInput] = useState('');
  const [query, setQuery]           = useState('');
  const [page, setPage]             = useState(1);
  const [sortKey, setSortKey]       = useState<SortKey>('latest_at');
  const [sortDir, setSortDir]       = useState<'asc' | 'desc'>('desc');

  useEffect(() => {
    const next = queryInput.trim();
    if (next === query) return;
    const id = window.setTimeout(() => {
      setQuery(next);
      setPage(1);
    }, 300);
    return () => window.clearTimeout(id);
  }, [queryInput, query]);

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir(DEFAULT_SORT_DIR[key]);
    }
    setPage(1);
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return stocks;
    const shouldSearchInitials = isKoreanInitialQuery(q);
    return stocks.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.ticker.toLowerCase().includes(q) ||
        (shouldSearchInitials && s.name_initials.includes(q)),
    );
  }, [stocks, query]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      let cmp = 0;
      if (sortKey === 'name') {
        cmp = a.name.localeCompare(b.name, 'ko');
      } else if (sortKey === 'latest_at') {
        cmp = a.latest_at < b.latest_at ? -1 : a.latest_at > b.latest_at ? 1 : 0;
      } else {
        cmp = a[sortKey] - b[sortKey];
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [filtered, sortKey, sortDir]);

  const totalPages = Math.ceil(sorted.length / PAGE_SIZE);
  const safePage   = totalPages > 0 ? Math.min(page, totalPages) : 1;
  const paged      = useMemo(
    () => sorted.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [sorted, safePage],
  );

  return (
    <section className="flex flex-col gap-6">
      <div className="flex items-end justify-between border-b border-white/[0.06] pb-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.32em] text-amber-300">
            screening stocks
          </p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-50">
            종목
          </h2>
        </div>

        <div className="flex flex-col items-end gap-2">
          <input
            className="h-10 rounded-md border border-slate-700/80 bg-slate-950/70 px-3 text-sm font-medium text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-amber-300/50 focus:ring-2 focus:ring-amber-300/20"
            onChange={(e) => setQueryInput(e.target.value)}
            placeholder="종목명, 초성 또는 티커"
            type="search"
            value={queryInput}
          />
          {!isLoading && !isError && stocks.length > 0 && (
            <span className="text-sm tabular-nums text-slate-500">
              {query
                ? `${filtered.length} / ${stocks.length}개 종목`
                : `${stocks.length}개 종목`}
            </span>
          )}
        </div>
      </div>

      {isError ? (
        <ErrorState onRetry={() => void refetch()} />
      ) : isLoading ? (
        <LoadingRows />
      ) : stocks.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="flex flex-col gap-4">
          <div className="overflow-hidden rounded-xl border border-white/[0.06] bg-slate-950/60 shadow-2xl shadow-black/30">
            <div
              className={`grid ${COL} border-b border-white/[0.06] bg-black/20 px-6 py-3`}
            >
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                종목
              </span>
              {SORT_COLUMNS.map(({ key, label, align }) => {
                const isActive = sortKey === key;
                return (
                  <button
                    className={[
                      'group/hdr flex items-center text-xs font-semibold uppercase tracking-[0.18em] transition',
                      align,
                      isActive
                        ? 'text-amber-300/90'
                        : 'text-slate-400 hover:text-slate-200',
                    ].join(' ')}
                    key={key}
                    onClick={() => handleSort(key)}
                    type="button"
                  >
                    {label}
                    <SortIcon active={isActive} dir={sortDir} />
                  </button>
                );
              })}
            </div>

            {paged.length === 0 ? (
              <div className="px-6 py-10 text-center text-sm text-slate-500">
                &ldquo;{query}&rdquo;에 해당하는 종목이 없습니다.
              </div>
            ) : (
              paged.map((stock) => (
                <StockRow key={stock.ticker} stock={stock} />
              ))
            )}
          </div>

          <PaginationControls
            disabled={false}
            onPageChange={(next) => setPage(next)}
            page={safePage}
            pageSize={PAGE_SIZE}
            total={filtered.length}
            totalPages={totalPages}
          />
        </div>
      )}
    </section>
  );
}

export default StockSummaryPage;
