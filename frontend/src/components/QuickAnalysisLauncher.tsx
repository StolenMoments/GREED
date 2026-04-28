import type { AxiosError } from 'axios';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { MODEL_OPTIONS, toAnalysisModel } from '../constants/analysisModels';
import { usePendingJobs } from '../contexts/PendingJobsContext';
import { useJobPolling, useTriggerAnalysis } from '../hooks/useJobs';
import type { AnalysisModel } from '../types';

interface QuickAnalysisLauncherProps {
  defaultModel: string;
  onAnalysisCreated?: () => void;
  runId: number;
  ticker: string;
}

function getAxiosMessage(error: unknown) {
  const axiosError = error as AxiosError<{ detail?: string }>;
  return axiosError.response?.data?.detail ?? '분석 잡을 시작하지 못했습니다.';
}

function getStatusMessage(status: string | undefined) {
  if (status === 'pending') {
    return '모델 분석 결과 파일을 기다리는 중입니다.';
  }

  if (status === 'done') {
    return '분석이 저장되었습니다. 새 결과를 열 수 있습니다.';
  }

  return '분석 잡이 완료되지 못했습니다.';
}

function QuickAnalysisLauncher({
  defaultModel,
  onAnalysisCreated,
  runId,
  ticker,
}: QuickAnalysisLauncherProps) {
  const [model, setModel] = useState<AnalysisModel>(() =>
    toAnalysisModel(defaultModel),
  );
  const [jobId, setJobId] = useState<number | null>(null);
  const [serverError, setServerError] = useState<string | null>(null);
  const triggerAnalysis = useTriggerAnalysis();
  const jobQuery = useJobPolling(jobId);
  const notifiedAnalysisIdRef = useRef<number | null>(null);
  const { addPendingJob } = usePendingJobs();
  const job = jobQuery.data;
  const isPending = triggerAnalysis.isPending || job?.status === 'pending';
  const hasFailure = job?.status === 'failed' || serverError || jobQuery.isError;
  const shouldShowStatus =
    Boolean(job) || Boolean(serverError) || jobQuery.isError || triggerAnalysis.isPending;
  const errorMessage =
    job?.error_message ?? serverError ?? (jobQuery.isError ? '잡 상태를 불러오지 못했습니다.' : null);

  const statusTone = useMemo(() => {
    if (job?.status === 'done') {
      return {
        border: 'border-emerald-200/20',
        bg: 'bg-emerald-950/20',
        text: 'text-emerald-100',
        label: '완료',
      };
    }

    if (hasFailure) {
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
      label: '진행 중',
    };
  }, [hasFailure, job?.status]);

  useEffect(() => {
    setModel(toAnalysisModel(defaultModel));
    setJobId(null);
    setServerError(null);
    notifiedAnalysisIdRef.current = null;
  }, [defaultModel, runId, ticker]);

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

  async function startAnalysis() {
    setJobId(null);
    setServerError(null);
    notifiedAnalysisIdRef.current = null;

    try {
      const createdJob = await triggerAnalysis.mutateAsync({
        ticker,
        run_id: runId,
        model,
      });
      setJobId(createdJob.id);
      addPendingJob(createdJob.id);
    } catch (error) {
      setJobId(null);
      setServerError(getAxiosMessage(error));
    }
  }

  return (
    <aside className="rounded-lg border border-amber-100/10 bg-slate-950/55 p-4">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-amber-300">
            quick analysis
          </p>
          <h3 className="mt-2 text-sm font-semibold text-slate-100">
            빠른 재분석
          </h3>
        </div>
        <span className="rounded-full border border-slate-700/80 px-2.5 py-1 text-xs font-semibold uppercase text-slate-400">
          {ticker}
        </span>
      </div>

      <p className="mt-3 text-sm leading-6 text-slate-400">
        현재 종목을 같은 Run에 다시 분석합니다.
      </p>

      <div
        className={[
          'mt-4',
          isPending ? 'pointer-events-none opacity-60' : '',
        ].join(' ')}
      >
        <span className="mb-2 block text-xs font-semibold text-slate-300">
          분석 엔진
        </span>
        <div className="grid grid-cols-3 gap-2">
          {MODEL_OPTIONS.map((option) => (
            <button
              className={[
                'rounded-md border px-2.5 py-2 text-left transition focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70',
                model === option.id
                  ? 'border-amber-300/80 bg-amber-300/10 text-amber-50'
                  : 'border-slate-800 bg-slate-950/50 text-slate-300 hover:border-slate-600 hover:bg-slate-900/40',
              ].join(' ')}
              key={option.id}
              onClick={() => setModel(option.id)}
              type="button"
            >
              <span className="block text-xs font-semibold leading-none">
                {option.label}
              </span>
              <span className="mt-1.5 block text-[0.68rem] text-slate-500">
                {option.provider}
              </span>
            </button>
          ))}
        </div>
      </div>

      <button
        className="mt-4 min-h-11 w-full rounded-md bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-amber-200 active:scale-[0.98] focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70 disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100 motion-reduce:transform-none"
        disabled={isPending}
        onClick={() => void startAnalysis()}
        type="button"
      >
        {isPending ? '분석 중' : '분석 시작'}
      </button>

      {shouldShowStatus ? (
        <div
          className={[
            'mt-4 rounded-lg border px-3 py-3 transition duration-300 ease-out motion-reduce:transition-none',
            statusTone.border,
            statusTone.bg,
          ].join(' ')}
        >
          <div className="flex flex-wrap items-center gap-2">
            {isPending ? (
              <span className="size-4 rounded-full border-2 border-amber-200/30 border-t-amber-200 animate-spin motion-reduce:animate-none" />
            ) : null}
            <p className={`text-sm font-semibold ${statusTone.text}`}>
              {job ? `Job #${job.id} · ${statusTone.label}` : statusTone.label}
            </p>
          </div>

          <p className="mt-2 text-xs leading-5 text-slate-300">
            {getStatusMessage(job?.status)}
          </p>

          {job?.status === 'done' && job.analysis_id ? (
            <Link
              className="mt-3 inline-flex rounded-md border border-emerald-100/25 px-3 py-2 text-xs font-semibold text-emerald-50 transition hover:bg-emerald-100/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-200/70"
              to={`/analyses/${job.analysis_id}`}
            >
              새 분석 보기
            </Link>
          ) : hasFailure ? (
            <button
              className="mt-3 rounded-md border border-rose-100/25 px-3 py-2 text-xs font-semibold text-rose-50 transition hover:bg-rose-100/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-200/70"
              onClick={() => void startAnalysis()}
              type="button"
            >
              다시 시도
            </button>
          ) : null}

          {errorMessage ? (
            <pre className="mt-3 whitespace-pre-wrap break-all rounded-md bg-slate-900/80 p-3 text-xs leading-5 text-slate-300">
              {errorMessage}
            </pre>
          ) : null}
        </div>
      ) : null}
    </aside>
  );
}

export default QuickAnalysisLauncher;
