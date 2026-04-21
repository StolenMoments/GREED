import type { AxiosError } from 'axios';
import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useJobPolling, useTriggerAnalysis } from '../hooks/useJobs';

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
  const [jobId, setJobId] = useState<number | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const [showValidation, setShowValidation] = useState(false);
  const triggerAnalysis = useTriggerAnalysis();
  const jobQuery = useJobPolling(jobId);
  const notifiedAnalysisIdRef = useRef<number | null>(null);

  const trimmedTicker = ticker.trim();
  const job = jobQuery.data;
  const isPending = triggerAnalysis.isPending || job?.status === 'pending';
  const isSubmitDisabled = isPending || trimmedTicker.length === 0;

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
    if (job?.status !== 'done' || !job.analysis_id) {
      return;
    }

    if (notifiedAnalysisIdRef.current === job.analysis_id) {
      return;
    }

    notifiedAnalysisIdRef.current = job.analysis_id;
    onAnalysisCreated?.();
  }, [job?.analysis_id, job?.status, onAnalysisCreated]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setShowValidation(true);
    setServerError(null);

    if (!trimmedTicker) {
      return;
    }

    try {
      const createdJob = await triggerAnalysis.mutateAsync({
        ticker: trimmedTicker,
        run_id: runId,
      });
      setJobId(createdJob.id);
      notifiedAnalysisIdRef.current = null;
    } catch (error) {
      setJobId(null);
      setServerError(getAxiosMessage(error));
    }
  }

  function handleRetry() {
    setJobId(null);
    setServerError(null);
    setShowValidation(false);
    notifiedAnalysisIdRef.current = null;
    triggerAnalysis.reset();
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
            종목 코드를 입력하면 이 실행에 연결된 분석 잡을 만들고 완료될 때까지 상태를 확인합니다.
          </p>
        </div>

        <form
          className="flex w-full flex-col gap-3 sm:max-w-md"
          onSubmit={(event) => void handleSubmit(event)}
        >
          <label className="block">
            <span className="text-sm font-semibold text-slate-200">Ticker</span>
            <div className="mt-2 flex gap-2">
              <input
                aria-invalid={showValidation && !trimmedTicker}
                className={[
                  'min-h-11 min-w-0 flex-1 rounded-md border bg-slate-950 px-3 py-2 text-sm font-semibold uppercase text-slate-100 transition focus:outline-none focus:ring-2 focus:ring-amber-300 disabled:cursor-not-allowed disabled:opacity-60',
                  showValidation && !trimmedTicker
                    ? 'border-rose-300/60'
                    : 'border-slate-700',
                ].join(' ')}
                disabled={isPending}
                onChange={(event) => setTicker(event.target.value.toUpperCase())}
                placeholder="005930"
                value={ticker}
              />
              <button
                className="min-h-11 shrink-0 rounded-md bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-amber-200 active:scale-[0.98] focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70 disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100 motion-reduce:transform-none"
                disabled={isSubmitDisabled}
                type="submit"
              >
                {isPending ? '분석 중' : '분석 시작'}
              </button>
            </div>
          </label>

          {showValidation && !trimmedTicker ? (
            <p className="text-sm text-rose-100">분석할 티커를 입력하세요.</p>
          ) : null}
        </form>
      </div>

      {job || serverError || jobQuery.isError ? (
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
                  ? '주봉 데이터 생성과 분석 저장을 진행 중입니다.'
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
                onClick={handleRetry}
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
