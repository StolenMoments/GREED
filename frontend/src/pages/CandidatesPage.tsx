import { useEffect, useState } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { fetchAllAnalyses } from '../api/analyses';
import { useAnalysis } from '../hooks/useAnalyses';
import {
  useCandidates,
  useLatestScanJob,
  useScanJobPolling,
  useTriggerScan,
} from '../hooks/useCandidates';
import { useTriggerAnalysis } from '../hooks/useJobs';
import { useRuns } from '../hooks/useRuns';
import { formatDateOnly } from '../utils/formatDate';
import type { CandidateScanJobStatus } from '../types';

const THRESHOLDS = [12, 13, 14] as const;
type Threshold = (typeof THRESHOLDS)[number];

const scanStatusStyles: Record<CandidateScanJobStatus, string> = {
  pending: 'border-sky-200/25 bg-sky-400/10 text-sky-100',
  running: 'border-sky-200/25 bg-sky-400/10 text-sky-100',
  done: 'border-emerald-200/25 bg-emerald-400/10 text-emerald-100',
  failed: 'border-rose-200/25 bg-rose-400/10 text-rose-100',
};

function LoadingRows() {
  return (
    <div className="divide-y divide-amber-100/10 overflow-hidden rounded-lg border border-amber-100/10 bg-slate-950/45">
      {Array.from({ length: 5 }, (_, index) => (
        <div
          className="grid gap-4 px-5 py-4 lg:grid-cols-[5rem_minmax(0,1fr)_4rem_7rem_7rem_7rem_7rem_5rem] lg:items-center"
          key={index}
        >
          {Array.from({ length: 8 }, (_, cellIndex) => (
            <div
              className="h-4 animate-pulse rounded bg-slate-800/80"
              key={cellIndex}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

function CandidatesPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const analysisIdParam = searchParams.get('analysis_id');
  const analysisId =
    analysisIdParam !== null &&
    Number.isInteger(Number(analysisIdParam)) &&
    Number(analysisIdParam) > 0
      ? Number(analysisIdParam)
      : undefined;

  const [threshold, setThreshold] = useState<Threshold>(12);
  const [activeJobId, setActiveJobId] = useState<number | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [tickerConfirm, setTickerConfirm] = useState<{
    ticker: string;
    name: string;
  } | null>(null);

  const { data: analysis, isError: isAnalysisError, isLoading: isAnalysisLoading } =
    useAnalysis(analysisId);
  const { data: latestJob } = useLatestScanJob(analysisId);
  const { data: scanJob } = useScanJobPolling(analysisId, activeJobId);
  const { data: candidates = [], isLoading: isCandidatesLoading } =
    useCandidates(analysisId, threshold);

  const triggerScanMutation = useTriggerScan();
  const triggerAnalysisMutation = useTriggerAnalysis();
  const { data: runs } = useRuns();

  // Resume polling if there is an in-progress job on mount
  useEffect(() => {
    if (!latestJob) return;
    if (latestJob.status === 'pending' || latestJob.status === 'running') {
      const t = latestJob.threshold;
      if (t === 12 || t === 13 || t === 14) {
        setThreshold(t);
      }
      setActiveJobId(latestJob.id);
    }
  }, [latestJob]);

  const isScanning =
    scanJob?.status === 'pending' || scanJob?.status === 'running';

  if (!analysisId) {
    return <Navigate replace to="/analyses" />;
  }

  async function handleScan() {
    setScanError(null);
    try {
      const job = await triggerScanMutation.mutateAsync({ analysisId: analysisId!, threshold });
      setActiveJobId(job.id);
    } catch (err) {
      setScanError(err instanceof Error ? err.message : '스캔 시작에 실패했습니다.');
    }
  }

  async function handleTickerClick(ticker: string, name: string) {
    try {
      const result = await fetchAllAnalyses({ q: ticker }, { page: 1, page_size: 1 });
      if (result.items.length > 0) {
        navigate(`/analyses/${result.items[0].id}`);
        return;
      }
    } catch {
      // fall through to confirm dialog
    }
    setTickerConfirm({ ticker, name });
  }

  async function handleConfirmAnalysis() {
    if (!tickerConfirm || !runs?.[0]) return;
    const { ticker } = tickerConfirm;
    setTickerConfirm(null);
    try {
      await triggerAnalysisMutation.mutateAsync({
        ticker,
        run_id: runs[0].id,
        model: 'claude',
      });
    } catch {
      // navigate to jobs regardless
    }
    navigate('/jobs');
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-slate-400">
        <Link className="transition hover:text-slate-200" to="/analyses">
          Analyses
        </Link>
        <span>/</span>
        {isAnalysisLoading ? (
          <span className="inline-block h-4 w-32 animate-pulse rounded bg-slate-800" />
        ) : analysis ? (
          <>
            <Link
              className="transition hover:text-slate-200"
              to={`/analyses/${analysis.id}`}
            >
              {analysis.name} ({analysis.ticker})
            </Link>
            <span>/</span>
          </>
        ) : null}
        <span className="text-slate-100">후보 종목</span>
      </div>

      {/* Analysis load error */}
      {isAnalysisError ? (
        <div className="rounded-lg border border-rose-200/20 bg-rose-950/20 px-5 py-4">
          <p className="text-sm font-semibold text-rose-100">
            분석 정보를 불러오지 못했습니다.
          </p>
        </div>
      ) : null}

      {/* Scan control panel */}
      <div className="rounded-lg border border-amber-100/10 bg-slate-950/45 px-6 py-5">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-slate-400">Threshold</span>
            <div className="flex rounded-lg border border-slate-700/80 bg-slate-950/70 p-0.5">
              {THRESHOLDS.map((t) => (
                <button
                  className={[
                    'rounded-md px-4 py-1.5 text-sm font-semibold transition',
                    threshold === t
                      ? 'bg-amber-300 text-slate-950'
                      : 'text-slate-300 hover:bg-slate-800 hover:text-slate-50',
                  ].join(' ')}
                  disabled={isScanning}
                  key={t}
                  onClick={() => { setThreshold(t); }}
                  type="button"
                >
                  {t}
                </button>
              ))}
            </div>
          </div>
          <button
            className="rounded-md bg-amber-300 px-5 py-2 text-sm font-semibold text-slate-950 transition hover:bg-amber-200 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isScanning || triggerScanMutation.isPending}
            onClick={() => { void handleScan(); }}
            type="button"
          >
            {isScanning ? '스캔 중...' : '스캔 시작'}
          </button>
        </div>
        {scanError ? (
          <p className="mt-3 text-sm text-rose-300">{scanError}</p>
        ) : null}
      </div>

      {/* In-progress status card (only while pending/running) */}
      {isScanning && scanJob ? (
        <div
          className={[
            'rounded-lg border px-5 py-4',
            scanStatusStyles[scanJob.status],
          ].join(' ')}
        >
          <div className="flex items-center gap-3">
            <svg
              aria-hidden="true"
              className="size-4 animate-spin"
              fill="none"
              viewBox="0 0 24 24"
              xmlns="http://www.w3.org/2000/svg"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                fill="currentColor"
              />
            </svg>
            <span className="text-sm font-semibold">
              스캔 중... · job #{scanJob.id} · {scanJob.status}
            </span>
          </div>
        </div>
      ) : null}

      {/* Failed error card */}
      {scanJob?.status === 'failed' ? (
        <div className="rounded-lg border border-rose-200/25 bg-rose-950/20 px-5 py-4">
          <p className="text-sm font-semibold text-rose-100">
            스캔 실패: {scanJob.error_message ?? '알 수 없는 오류'}
          </p>
        </div>
      ) : null}

      {/* Candidates table */}
      <div className="flex flex-col gap-3">
        {candidates.length > 0 ? (
          <p className="text-sm text-slate-400">
            스캔 날짜: {formatDateOnly(candidates[0].scan_date)} · {candidates.length}개 종목
          </p>
        ) : null}

        {isCandidatesLoading ? (
          <LoadingRows />
        ) : candidates.length === 0 ? (
          <div className="rounded-lg border border-amber-100/10 bg-slate-950/45 px-6 py-12 text-center">
            <p className="text-sm font-semibold text-slate-100">
              스캔 결과가 없습니다.
            </p>
            <p className="mt-2 text-sm text-slate-400">
              threshold를 선택하고 스캔을 시작하세요.
            </p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-amber-100/10 bg-slate-950/45">
            <div className="hidden grid-cols-[5rem_minmax(0,1fr)_4rem_7rem_7rem_7rem_7rem_5rem] gap-4 border-b border-amber-100/10 px-5 py-3 lg:grid">
              {['티커', '종목명', '점수', '현재가', '진입가', '목표가', '손절가', '진입갭'].map(
                (label, i) => (
                  <span
                    className={[
                      'text-xs font-semibold uppercase tracking-wide text-slate-500',
                      i >= 2 ? 'text-right' : '',
                    ].join(' ')}
                    key={label}
                  >
                    {label}
                  </span>
                ),
              )}
            </div>
            <div className="divide-y divide-amber-100/10">
              {candidates.map((c) => (
                <button
                  className="grid w-full gap-4 px-5 py-4 text-left transition hover:bg-amber-100/[0.035] focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-amber-300/70 lg:grid-cols-[5rem_minmax(0,1fr)_4rem_7rem_7rem_7rem_7rem_5rem] lg:items-center"
                  key={c.id}
                  onClick={() => { void handleTickerClick(c.ticker, c.name); }}
                  type="button"
                >
                  <span className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-300">
                    {c.ticker}
                  </span>
                  <span className="text-sm font-semibold text-slate-100">
                    {c.name}
                  </span>
                  <span className="text-right text-sm tabular-nums text-slate-300">
                    {c.score}
                  </span>
                  <span className="text-right text-sm tabular-nums text-slate-300">
                    {c.current_close.toLocaleString()}
                  </span>
                  <span className="text-right text-sm tabular-nums text-slate-300">
                    {c.entry_price.toLocaleString()}
                  </span>
                  <span className="text-right text-sm tabular-nums text-emerald-300">
                    {c.target_price.toLocaleString()}
                  </span>
                  <span className="text-right text-sm tabular-nums text-rose-300">
                    {c.stop_price.toLocaleString()}
                  </span>
                  <span
                    className={[
                      'text-right text-sm tabular-nums font-semibold',
                      c.entry_gap_pct <= 0 ? 'text-emerald-300' : 'text-slate-300',
                    ].join(' ')}
                  >
                    {c.entry_gap_pct > 0 ? '+' : ''}
                    {c.entry_gap_pct.toFixed(1)}%
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Ticker confirm dialog */}
      {tickerConfirm ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm">
          <div className="mx-4 w-full max-w-sm rounded-lg border border-amber-100/10 bg-slate-900 p-6 shadow-2xl">
            <h3 className="text-base font-semibold text-slate-100">
              분석 기록 없음
            </h3>
            <p className="mt-2 text-sm text-slate-400">
              <span className="font-semibold text-amber-300">
                {tickerConfirm.ticker}
              </span>{' '}
              {tickerConfirm.name}의 분석 기록이 없습니다. 분석을 시작하시겠습니까?
            </p>
            <div className="mt-5 flex justify-end gap-3">
              <button
                className="rounded-md border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-300 transition hover:bg-slate-800"
                onClick={() => { setTickerConfirm(null); }}
                type="button"
              >
                취소
              </button>
              <button
                className="rounded-md bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-amber-200 disabled:opacity-50"
                disabled={triggerAnalysisMutation.isPending || !runs?.[0]}
                onClick={() => { void handleConfirmAnalysis(); }}
                type="button"
              >
                {triggerAnalysisMutation.isPending ? '시작 중...' : '분석 시작'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default CandidatesPage;
