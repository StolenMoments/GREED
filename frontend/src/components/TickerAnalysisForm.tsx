import type { AxiosError } from 'axios';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent, KeyboardEvent } from 'react';
import { Link } from 'react-router-dom';
import { getTicker, searchTickers } from '../api/tickers';
import type { TickerSearchResult } from '../api/tickers';
import { MODEL_OPTIONS } from '../constants/analysisModels';
import { usePendingJobs } from '../contexts/PendingJobsContext';
import { useJobPolling, useRunJobs, useTriggerAnalysis } from '../hooks/useJobs';
import type { AnalysisModel } from '../types';

function isKorean(text: string): boolean {
  return /[가-힣ㄱ-ㅎ]/.test(text);
}

function isSixDigitTicker(text: string): boolean {
  return /^\d{6}$/.test(text.trim());
}

function isSingleLetterTicker(text: string): boolean {
  return /^[A-Z]$/.test(text.trim());
}

function isLikelyUsTicker(text: string): boolean {
  return /^[A-Z][A-Z.-]*$/.test(text.trim());
}

type TickerLookupState =
  | { status: 'idle' }
  | { status: 'loading'; code: string }
  | { status: 'found'; code: string; name: string }
  | { status: 'not-found'; code: string };

interface TickerAnalysisFormProps {
  runId: number;
  onAnalysisCreated?: () => void;
}

function getAxiosMessage(error: unknown) {
  const axiosError = error as AxiosError<{ detail?: string }>;
  return axiosError.response?.data?.detail ?? '분석 잡을 시작하지 못했습니다.';
}

function TickerAnalysisForm({
  runId,
  onAnalysisCreated,
}: TickerAnalysisFormProps) {
  const [ticker, setTicker] = useState('');
  const [model, setModel] = useState<AnalysisModel>('claude');
  const [jobId, setJobId] = useState<number | null>(null);
  const [dismissedJobId, setDismissedJobId] = useState<number | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [showValidation, setShowValidation] = useState(false);
  const [suggestions, setSuggestions] = useState<TickerSearchResult[]>([]);
  const [isSearchingSuggestions, setIsSearchingSuggestions] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [activeSuggestion, setActiveSuggestion] = useState(-1);
  const [tickerLookup, setTickerLookup] = useState<TickerLookupState>({ status: 'idle' });
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lookupDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const latestInputRef = useRef('');
  const triggerAnalysis = useTriggerAnalysis();
  const runJobsQuery = useRunJobs(runId);
  const latestRunJob = runJobsQuery.data?.find((runJob) => runJob.id !== dismissedJobId);
  const trackedJobId = jobId ?? latestRunJob?.id ?? null;
  const jobQuery = useJobPolling(trackedJobId);
  const notifiedAnalysisIdRef = useRef<number | null>(null);

  const { addPendingJob } = usePendingJobs();
  const trimmedTicker = ticker.trim();
  const job = jobQuery.data ?? latestRunJob;
  const isJobPending = job?.status === 'pending';
  const isPending = triggerAnalysis.isPending || isJobPending;
  const hasConfirmedTicker =
    tickerLookup.status === 'found' && tickerLookup.code === trimmedTicker;
  const minimumSearchLength = isKorean(trimmedTicker) ? 2 : 1;
  const canSearchTicker = trimmedTicker.length >= minimumSearchLength;
  const hasNoTickerMatch =
    canSearchTicker &&
    !isSearchingSuggestions &&
    suggestions.length === 0 &&
    !hasConfirmedTicker &&
    tickerLookup.status !== 'loading';
  const hasUnselectedSuggestion = suggestions.length > 0 && !hasConfirmedTicker;
  const needsKoreanNameSelection = isKorean(ticker) && !hasConfirmedTicker;
  const needsLongerTickerInput = isSingleLetterTicker(trimmedTicker) && !hasConfirmedTicker;
  const isSubmitDisabled =
    triggerAnalysis.isPending ||
    !trimmedTicker ||
    needsLongerTickerInput ||
    tickerLookup.status === 'loading' ||
    tickerLookup.status === 'not-found' ||
    isSearchingSuggestions ||
    hasUnselectedSuggestion ||
    needsKoreanNameSelection ||
    !hasConfirmedTicker;

  const statusTone = useMemo(() => {
    if (job?.status === 'done') {
      return {
        border: 'border-emerald-200/20',
        bg: 'bg-emerald-950/20',
        text: 'text-emerald-100',
        label: '완료',
      };
    }

    if (job?.status === 'failed' || serverError || jobQuery.isError) {
      return {
        border: 'border-rose-200/20',
        bg: 'bg-rose-950/20',
        text: 'text-rose-100',
        label: '실패',
      };
    }

    return {
      border: 'border-amber-100/15',
      bg: 'bg-slate-950/55',
      text: 'text-slate-200',
      label: '대기',
    };
  }, [job?.status, jobQuery.isError, serverError]);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (lookupDebounceRef.current) clearTimeout(lookupDebounceRef.current);
    };
  }, []);

  useEffect(() => {
    if (job?.status !== 'done' || !job.analysis_id) {
      return;
    }

    if (notifiedAnalysisIdRef.current === job.analysis_id) {
      return;
    }

    notifiedAnalysisIdRef.current = job.analysis_id;
    onAnalysisCreated?.();
  }, [job?.analysis_id, job?.status, onAnalysisCreated]);

  function handleTickerChange(value: string) {
    const next = isKorean(value) ? value : value.toUpperCase();
    const nextTrimmed = next.trim();
    latestInputRef.current = nextTrimmed;
    setTicker(next);
    setActiveSuggestion(-1);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (lookupDebounceRef.current) clearTimeout(lookupDebounceRef.current);
    setSuggestions([]);
    setShowSuggestions(false);
    setIsSearchingSuggestions(false);

    const minimumSearchLength = isKorean(nextTrimmed) ? 2 : 1;
    if (nextTrimmed.length >= minimumSearchLength) {
      setTickerLookup({ status: 'idle' });
      setIsSearchingSuggestions(true);
      debounceRef.current = setTimeout(() => {
        const query = nextTrimmed;
        searchTickers(query)
          .then((r) => {
            if (latestInputRef.current !== query) return;
            setSuggestions(r);
            setShowSuggestions(r.length > 0);
          })
          .catch(() => {
            if (latestInputRef.current === query) {
              setSuggestions([]);
              setShowSuggestions(false);
            }
          })
          .finally(() => {
            if (latestInputRef.current === query) {
              setIsSearchingSuggestions(false);
            }
          });
      }, 200);
    } else {
      setSuggestions([]);
      setShowSuggestions(false);
    }

    if (isSixDigitTicker(nextTrimmed)) {
      setTickerLookup({ status: 'loading', code: nextTrimmed });
      lookupDebounceRef.current = setTimeout(() => {
        getTicker(nextTrimmed)
          .then((result) => {
            if (latestInputRef.current === result.code) {
              setTickerLookup({ status: 'found', code: result.code, name: result.name });
            }
          })
          .catch(() => {
            if (latestInputRef.current === nextTrimmed) {
              setTickerLookup({ status: 'not-found', code: nextTrimmed });
            }
          });
      }, 200);
    } else if (!isKorean(value) && isLikelyUsTicker(nextTrimmed)) {
      setTickerLookup({ status: 'loading', code: nextTrimmed });
      lookupDebounceRef.current = setTimeout(() => {
        getTicker(nextTrimmed)
          .then((result) => {
            if (latestInputRef.current === result.code) {
              setTickerLookup({ status: 'found', code: result.code, name: result.name });
            }
          })
          .catch(() => {
            if (latestInputRef.current === nextTrimmed) {
              setTickerLookup({ status: 'idle' });
            }
          });
      }, 200);
    } else if (!isKorean(value)) {
      setTickerLookup({ status: 'idle' });
    }
  }

  function selectSuggestion(result: TickerSearchResult) {
    setTicker(result.code);
    latestInputRef.current = result.code;
    setTickerLookup({ status: 'found', code: result.code, name: result.name });
    setSuggestions([]);
    setShowSuggestions(false);
    setActiveSuggestion(-1);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!showSuggestions) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveSuggestion((prev) => Math.min(prev + 1, suggestions.length - 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveSuggestion((prev) => Math.max(prev - 1, -1));
    } else if (event.key === 'Enter' && suggestions.length > 0) {
      event.preventDefault();
      selectSuggestion(suggestions[Math.max(activeSuggestion, 0)]);
    } else if (event.key === 'Escape') {
      setShowSuggestions(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setShowValidation(true);
    setServerError(null);

    if (isSubmitDisabled) {
      return;
    }

    try {
      const createdJob = await triggerAnalysis.mutateAsync({
        ticker: trimmedTicker,
        run_id: runId,
        model,
      });
      setDismissedJobId(null);
      setJobId(createdJob.id);
      addPendingJob(createdJob.id);
      notifiedAnalysisIdRef.current = null;
    } catch (error) {
      setJobId(null);
      setServerError(getAxiosMessage(error));
    }
  }

  async function handleRetry() {
    const retryTicker = trimmedTicker || job?.ticker || '';
    setDismissedJobId(job?.id ?? null);
    setJobId(null);
    setServerError(null);
    setShowValidation(false);
    notifiedAnalysisIdRef.current = null;

    if (!retryTicker) return;

    try {
      const createdJob = await triggerAnalysis.mutateAsync({
        ticker: retryTicker,
        run_id: runId,
        model,
      });
      setDismissedJobId(null);
      setJobId(createdJob.id);
      addPendingJob(createdJob.id);
      notifiedAnalysisIdRef.current = null;
    } catch (error) {
      setJobId(null);
      setServerError(getAxiosMessage(error));
    }
  }

  return (
    <section className="rounded-lg border border-amber-100/10 bg-slate-950/50 p-5 shadow-2xl shadow-slate-950/20">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-amber-300">
            trigger analysis
          </p>
          <h3 className="mt-2 text-xl font-semibold tracking-tight text-slate-50">
            티커 분석 실행
          </h3>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
            국내 종목코드·종목명 또는 미국 티커를 입력하면 이 실행에 연결된 분석 잡을 만들고 완료될 때까지 상태를 확인합니다.
          </p>
        </div>

        <form
          className="flex w-full flex-col gap-3 sm:max-w-md"
          onSubmit={(event) => void handleSubmit(event)}
        >
          <div className={triggerAnalysis.isPending ? 'pointer-events-none opacity-60' : ''}>
            <span className="mb-2 block text-sm font-semibold text-slate-200">분석 엔진</span>
            <div className="grid grid-cols-3 gap-2">
              {MODEL_OPTIONS.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setModel(opt.id)}
                  className={[
                    'rounded-lg border px-4 py-3 text-left transition duration-150',
                    model === opt.id
                      ? 'border-amber-300/80 bg-amber-300/10 text-amber-50'
                      : 'border-slate-800 bg-slate-950/50 text-slate-300 hover:border-slate-600 hover:bg-slate-900/40',
                  ].join(' ')}
                >
                  <span className="block text-sm font-semibold leading-none">{opt.label}</span>
                  <span className="mt-1.5 block text-xs text-slate-400">{opt.provider}</span>
                </button>
              ))}
            </div>
          </div>

          <label className="block">
            <span className="text-sm font-semibold text-slate-200">Ticker</span>
            <div className="mt-2 flex gap-2">
              <div ref={containerRef} className="relative min-w-0 flex-1">
                <input
                  aria-autocomplete="list"
                  aria-expanded={showSuggestions}
                  aria-invalid={showValidation && !trimmedTicker}
                  className={[
                    'min-h-11 w-full rounded-md border bg-slate-950 px-3 py-2 text-sm font-semibold text-slate-100 transition focus:outline-none focus:ring-2 focus:ring-amber-300/70 disabled:cursor-not-allowed disabled:opacity-60',
                    isKorean(ticker) ? '' : 'uppercase',
                    showValidation && !trimmedTicker
                      ? 'border-rose-300/60'
                      : 'border-slate-700',
                  ].join(' ')}
                  disabled={triggerAnalysis.isPending}
                  onChange={(event) => handleTickerChange(event.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="005930 · AAPL · 삼성전자"
                  value={ticker}
                />
                {showSuggestions && suggestions.length > 0 && (
                  <ul
                    role="listbox"
                    className="animate-dropdown-in absolute z-50 mt-1.5 w-full overflow-hidden rounded-lg border border-[oklch(0.26_0.015_80)] bg-[oklch(0.12_0.012_80)] py-1 shadow-2xl shadow-black/50"
                  >
                    {suggestions.map((s, i) => (
                      <li key={s.code} role="option" aria-selected={i === activeSuggestion}>
                        <button
                          type="button"
                          onMouseDown={() => selectSuggestion(s)}
                          className={[
                            'flex w-full items-center justify-between gap-4 px-3 py-2.5 text-sm transition-colors duration-75',
                            i === activeSuggestion
                              ? 'bg-[oklch(0.82_0.16_80_/_0.13)] text-[oklch(0.92_0.03_80)]'
                              : 'text-[oklch(0.78_0.015_80)] hover:bg-[oklch(0.82_0.16_80_/_0.08)] hover:text-[oklch(0.88_0.02_80)]',
                          ].join(' ')}
                        >
                          <span className="truncate font-medium">{s.name}</span>
                          <span className="flex shrink-0 items-center gap-2">
                            <span className="rounded border border-[oklch(0.35_0.018_80)] px-1.5 py-0.5 text-[0.65rem] font-semibold text-[oklch(0.58_0.028_80)]">
                              {s.market}
                            </span>
                            <span className="tabular-nums text-xs tracking-wider text-[oklch(0.48_0.025_80)]">
                              {s.code}
                            </span>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="mt-2 min-h-5" aria-live="polite">
                  {tickerLookup.status === 'loading' ? (
                    <span className="text-xs font-medium text-[oklch(0.72_0.06_80)]">
                      종목 확인 중
                    </span>
                  ) : tickerLookup.status === 'found' ? (
                    <span className="inline-flex max-w-full items-center gap-2 rounded-md border border-[oklch(0.82_0.16_80_/_0.22)] bg-[oklch(0.82_0.16_80_/_0.08)] px-2.5 py-1 text-xs font-semibold text-[oklch(0.88_0.05_80)]">
                      <span className="truncate">{tickerLookup.name}</span>
                      <span className="shrink-0 tabular-nums text-[oklch(0.62_0.04_80)]">
                        {tickerLookup.code}
                      </span>
                    </span>
                  ) : tickerLookup.status === 'not-found' ? (
                    <span className="text-xs font-medium text-slate-500">
                      종목명을 찾지 못했습니다
                    </span>
                  ) : hasNoTickerMatch ? (
                    <span className="text-xs font-medium text-slate-500">
                      조회되는 종목이 없습니다
                    </span>
                  ) : null}
                </div>
              </div>
              <button
                className="min-h-11 shrink-0 rounded-md bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-amber-200 active:scale-[0.98] focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70 disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100 motion-reduce:transform-none"
                disabled={isSubmitDisabled}
                type="submit"
              >
                {triggerAnalysis.isPending ? '요청 중' : '분석 시작'}
              </button>
            </div>
          </label>

          {showValidation && !trimmedTicker ? (
            <p className="text-sm text-rose-100">분석할 티커를 입력하세요.</p>
          ) : null}
        </form>
      </div>

      {job || serverError || jobQuery.isError || triggerAnalysis.isPending ? (
        <div
          className={[
            'mt-5 rounded-lg border px-4 py-4 transition duration-300 ease-out motion-reduce:transition-none',
            statusTone.border,
            statusTone.bg,
          ].join(' ')}
        >
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-3">
                {isPending ? (
                  <span className="size-4 rounded-full border-2 border-amber-200/30 border-t-amber-200 animate-spin motion-reduce:animate-none" />
                ) : null}
                <p className={`text-sm font-semibold ${statusTone.text}`}>
                  {job ? `Job #${job.id} · ${statusTone.label}` : statusTone.label}
                </p>
                {job ? (
                  <span className="rounded-full border border-slate-700/80 px-2.5 py-1 text-xs font-semibold uppercase text-slate-400">
                    {job.ticker}
                  </span>
                ) : null}
              </div>

              <p className="mt-2 text-sm leading-6 text-slate-300">
                {job?.status === 'pending'
                  ? '모델 분석 결과 파일을 기다리는 중입니다.'
                  : job?.status === 'done'
                    ? '분석이 저장되었습니다. 목록이 곧 최신 상태로 갱신됩니다.'
                    : '분석 잡이 완료되지 못했습니다.'}
              </p>
            </div>

            {job?.status === 'done' && job.analysis_id ? (
              <Link
                className="w-fit rounded-md border border-emerald-100/25 px-4 py-2 text-sm font-semibold text-emerald-50 transition hover:bg-emerald-100/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-200/70"
                to={`/analyses/${job.analysis_id}`}
              >
                분석 결과 보기
              </Link>
            ) : job?.status === 'failed' || serverError || jobQuery.isError ? (
              <button
                className="w-fit rounded-md border border-rose-100/25 px-4 py-2 text-sm font-semibold text-rose-50 transition hover:bg-rose-100/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-200/70"
                onClick={() => void handleRetry()}
                type="button"
              >
                다시 시도
              </button>
            ) : null}
          </div>

          {job?.error_message || serverError || jobQuery.isError ? (
            <pre className="mt-4 whitespace-pre-wrap break-all rounded-md bg-slate-900/80 p-3 text-xs leading-5 text-slate-300">
              {job?.error_message ??
                serverError ??
                '잡 상태를 불러오지 못했습니다.'}
            </pre>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default TickerAnalysisForm;
