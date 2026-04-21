import type { AxiosError } from 'axios';
import { useEffect, useMemo, useState } from 'react';
import MarkdownRenderer from './MarkdownRenderer';
import ParsedSummaryCard from './ParsedSummaryCard';
import { useCreateAnalysis } from '../hooks/useAnalyses';
import { useCreateRun, useRuns } from '../hooks/useRuns';
import type { Analysis, CreateAnalysisPayload } from '../types';
import { parseMarkdown } from '../utils/parseMarkdown';

const modelOptions = ['GPT', 'Gemini', 'Claude'] as const;

const starterMarkdown = `### 1. 현재 구조 요약
- 추세: 상승
- 구름대 위치: 구름 위
- MA 배열: 정배열

### 2. 매매 판단
**매수**

| 구분 | 조건 | 가격대 |
| --- | --- | --- |
| 진입 조건 | 눌림 확인 | 75,000 |
| 1차 목표 | 저항 돌파 | 82,000 |
| 손절 기준 | 지지 이탈 | 70,000 |
`;

interface ManualInputModalProps {
  defaultRunId?: number;
  isOpen: boolean;
  onClose: () => void;
  onSaved?: (analysis: Analysis) => void;
}

function ManualInputModal({
  defaultRunId,
  isOpen,
  onClose,
  onSaved,
}: ManualInputModalProps) {
  const { data: runs = [], isLoading: isRunsLoading } = useRuns();
  const createRunMutation = useCreateRun();
  const createAnalysisMutation = useCreateAnalysis();
  const [step, setStep] = useState(1);
  type ModelOption = (typeof modelOptions)[number];
  const [model, setModel] = useState<ModelOption>(modelOptions[0]);
  const [runMode, setRunMode] = useState<'existing' | 'new'>('existing');
  const [selectedRunId, setSelectedRunId] = useState<number | undefined>(
    defaultRunId,
  );
  const [ticker, setTicker] = useState('');
  const [name, setName] = useState('');
  const [markdown, setMarkdown] = useState(starterMarkdown);
  const [showErrors, setShowErrors] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const parsed = useMemo(() => parseMarkdown(markdown), [markdown]);
  const isSaving = createRunMutation.isPending || createAnalysisMutation.isPending;
  const resolvedRunId =
    runMode === 'existing'
      ? selectedRunId ?? defaultRunId ?? runs[0]?.id
      : undefined;

  useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !isSaving) onClose();
    }
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isSaving, onClose]);

  useEffect(() => {
    if (!isOpen) return;

    setStep(1);
    setModel(modelOptions[0]);
    setRunMode('existing');
    setSelectedRunId(defaultRunId);
    setTicker('');
    setName('');
    setMarkdown(starterMarkdown);
    setShowErrors(false);
    setServerError(null);
  }, [defaultRunId, isOpen]);

  useEffect(() => {
    if (selectedRunId || !defaultRunId) return;
    setSelectedRunId(defaultRunId);
  }, [defaultRunId, selectedRunId]);

  if (!isOpen) {
    return null;
  }

  const canAdvanceFromStepTwo = runMode === 'new' || Boolean(resolvedRunId);

  async function handleSave() {
    setServerError(null);
    setShowErrors(true);

    if (!ticker.trim() || !name.trim() || !parsed.success) {
      return;
    }

    try {
      const run =
        runMode === 'new'
          ? await createRunMutation.mutateAsync({ memo: 'manual input' })
          : undefined;
      const runId = run?.id ?? resolvedRunId;

      if (!runId) {
        setServerError('저장할 실행을 선택하세요.');
        return;
      }

      const payload: CreateAnalysisPayload = {
        run_id: runId,
        ticker: ticker.trim().toUpperCase(),
        name: name.trim(),
        model,
        markdown,
        judgment: parsed.data.judgment,
        trend: parsed.data.trend,
        cloud_position: parsed.data.cloud_position,
        ma_alignment: parsed.data.ma_alignment,
        entry_price: parsed.data.entry_price,
        target_price: parsed.data.target_price,
        stop_loss: parsed.data.stop_loss,
      };

      const analysis = await createAnalysisMutation.mutateAsync(payload);
      onSaved?.(analysis);
      onClose();
    } catch (error) {
      const axiosError = error as AxiosError<{
        detail?: string;
        failed_fields?: string[];
      }>;
      const failedFields = axiosError.response?.data?.failed_fields;
      setServerError(
        failedFields?.length
          ? `파싱 실패: ${failedFields.join(', ')}`
          : axiosError.response?.data?.detail ?? '수동 분석 저장에 실패했습니다.',
      );
    }
  }

  return (
    <div
      aria-labelledby="manual-modal-title"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-4 py-6 backdrop-blur-sm"
      role="dialog"
    >
      <div className="flex max-h-full w-full max-w-5xl flex-col overflow-hidden rounded-lg border border-amber-100/15 bg-slate-950 shadow-2xl shadow-slate-950">
        <header className="flex items-start justify-between gap-4 border-b border-amber-100/10 px-6 py-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.28em] text-amber-300">
              manual input
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-50" id="manual-modal-title">
              수동 분석 입력
            </h2>
          </div>
          <button
            className="rounded-md border border-slate-700 px-3 py-2 text-sm font-semibold text-slate-200 transition hover:bg-slate-800"
            onClick={onClose}
            type="button"
          >
            닫기
          </button>
        </header>

        <div className="border-b border-amber-100/10 px-6 py-4">
          <ol className="grid grid-cols-3 gap-3 text-sm font-semibold">
            {['모델 선택', '실행 선택', '분석 입력'].map((label, index) => {
              const current = index + 1;

              return (
                <li
                  className={[
                    'rounded-md border px-3 py-2',
                    step === current
                      ? 'border-amber-300 bg-amber-300 text-slate-950'
                      : 'border-slate-800 bg-slate-950/60 text-slate-400',
                  ].join(' ')}
                  key={label}
                >
                  {current}. {label}
                </li>
              );
            })}
          </ol>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {step === 1 ? (
            <div className="grid gap-3 sm:grid-cols-3">
              {modelOptions.map((option) => (
                <button
                  className={[
                    'rounded-lg border px-4 py-5 text-left transition',
                    model === option
                      ? 'border-amber-300 bg-amber-300/10 text-amber-50'
                      : 'border-slate-800 bg-slate-950/50 text-slate-300 hover:border-slate-600',
                  ].join(' ')}
                  key={option}
                  onClick={() => setModel(option)}
                  type="button"
                >
                  <span className="block text-base font-semibold">{option}</span>
                  <span className="mt-2 block text-sm text-slate-400">
                    {option === 'GPT' ? 'OpenAI' : option === 'Gemini' ? 'Google' : 'Anthropic'}
                  </span>
                </button>
              ))}
            </div>
          ) : null}

          {step === 2 ? (
            <div className="grid gap-4 md:grid-cols-2">
              <div
                className={[
                  'rounded-lg border p-4 text-left transition',
                  runMode === 'existing'
                    ? 'border-amber-300 bg-amber-300/10'
                    : 'border-slate-800 bg-slate-950/50 hover:border-slate-600',
                ].join(' ')}
              >
                <button
                  className="text-left text-base font-semibold text-slate-100"
                  onClick={() => setRunMode('existing')}
                  type="button"
                >
                  기존 실행에 추가
                </button>
                <select
                  className="mt-4 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-amber-300"
                  disabled={isRunsLoading || runs.length === 0}
                  onChange={(event) => {
                    setRunMode('existing');
                    setSelectedRunId(Number(event.target.value));
                  }}
                  value={resolvedRunId ?? ''}
                >
                  {runs.length === 0 ? (
                    <option value="">실행 없음</option>
                  ) : (
                    runs.map((run) => (
                      <option key={run.id} value={run.id}>
                        #{run.id} {run.memo ?? 'memo 없음'}
                      </option>
                    ))
                  )}
                </select>
              </div>

              <button
                className={[
                  'rounded-lg border p-4 text-left transition',
                  runMode === 'new'
                    ? 'border-amber-300 bg-amber-300/10'
                    : 'border-slate-800 bg-slate-950/50 hover:border-slate-600',
                ].join(' ')}
                onClick={() => setRunMode('new')}
                type="button"
              >
                <span className="text-base font-semibold text-slate-100">
                  신규 실행 생성
                </span>
                <span className="mt-4 block text-sm leading-6 text-slate-400">
                  저장 시 새 실행을 만든 뒤 이 분석을 연결합니다.
                </span>
              </button>
            </div>
          ) : null}

          {step === 3 ? (
            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
              <div className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field
                    error={showErrors && !ticker.trim()}
                    label="Ticker"
                    onChange={setTicker}
                    value={ticker}
                  />
                  <Field
                    error={showErrors && !name.trim()}
                    label="Name"
                    onChange={setName}
                    value={name}
                  />
                </div>

                <label className="block">
                  <span className="text-sm font-semibold text-slate-200">
                    Markdown
                  </span>
                  <textarea
                    className={[
                      'mt-2 h-72 w-full resize-y rounded-lg border bg-slate-950 px-4 py-3 font-mono text-sm leading-6 text-slate-100 focus:outline-none focus:ring-2 focus:ring-amber-300',
                      showErrors && !parsed.success
                        ? 'border-rose-300/60'
                        : 'border-slate-700',
                    ].join(' ')}
                    onChange={(event) => setMarkdown(event.target.value)}
                    value={markdown}
                  />
                </label>

                <div className="rounded-lg border border-slate-800 bg-slate-950/45 p-4">
                  <MarkdownRenderer markdown={markdown} />
                </div>
              </div>

              <ParsedSummaryCard parsed={parsed} showErrors={showErrors} />
            </div>
          ) : null}

          {serverError ? (
            <p className="mt-4 rounded-md border border-rose-300/30 bg-rose-950/30 px-4 py-3 text-sm text-rose-100">
              {serverError}
            </p>
          ) : null}
        </div>

        <footer className="flex items-center justify-between gap-4 border-t border-amber-100/10 px-6 py-4">
          <button
            className="rounded-md border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-200 transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
            disabled={step === 1 || isSaving}
            onClick={() => setStep((current) => Math.max(1, current - 1))}
            type="button"
          >
            이전
          </button>

          {step < 3 ? (
            <button
              className="rounded-md bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-amber-200 disabled:cursor-not-allowed disabled:opacity-40"
              disabled={step === 2 && !canAdvanceFromStepTwo}
              onClick={() => setStep((current) => current + 1)}
              type="button"
            >
              다음
            </button>
          ) : (
            <button
              className="rounded-md bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-amber-200 disabled:cursor-not-allowed disabled:opacity-40"
              disabled={isSaving}
              onClick={() => void handleSave()}
              type="button"
            >
              {isSaving ? '저장 중' : '저장'}
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}

function Field({
  error,
  label,
  onChange,
  value,
}: {
  error: boolean;
  label: string;
  onChange: (value: string) => void;
  value: string;
}) {
  return (
    <label className="block">
      <span className="text-sm font-semibold text-slate-200">{label}</span>
      <input
        className={[
          'mt-2 w-full rounded-md border bg-slate-950 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-amber-300',
          error ? 'border-rose-300/60' : 'border-slate-700',
        ].join(' ')}
        onChange={(event) => onChange(event.target.value)}
        value={value}
      />
    </label>
  );
}

export default ManualInputModal;
