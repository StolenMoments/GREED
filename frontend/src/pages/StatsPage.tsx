import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import {
  fetchBySignal,
  fetchStatsByModel,
  type ModelStat,
  type SignalCell,
  type SignalMatrixStat,
} from '../api/stats';

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

function useStatsByModel() {
  return useQuery({
    queryKey: ['stats', 'by-model'],
    queryFn: fetchStatsByModel,
  });
}

function useBySignal(model: string) {
  return useQuery({
    queryKey: ['stats', 'by-signal', model],
    queryFn: () => fetchBySignal(model),
    enabled: !!model,
  });
}

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

const JUDGMENT_COLORS: Record<string, string> = {
  매수: 'bg-emerald-500',
  홀드: 'bg-slate-500',
  매도: 'bg-rose-500',
};

const OUTCOME_COLORS: Record<string, string> = {
  목표달성: 'bg-emerald-500',
  손절: 'bg-rose-500',
  진행중: 'bg-amber-400',
  판정불가: 'bg-slate-600',
};

function pct(value: number | null, digits = 1): string {
  if (value === null) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`;
}

function ratio(value: number | null, digits = 1): string {
  if (value === null) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

function weeks(value: number | null): string {
  if (value === null) return '—';
  return `${value.toFixed(1)}주`;
}

/** HSL background color for a win_rate in [0, 1]. Null → gray. */
function cellBg(winRate: number | null): string {
  if (winRate === null) return 'hsl(220, 10%, 12%)';
  const hue = Math.round(winRate * 120);
  return `hsl(${hue}, 55%, 18%)`;
}

// ---------------------------------------------------------------------------
// Section 1 — by-model cards
// ---------------------------------------------------------------------------

function MiniBar({
  data,
  colors,
  total,
}: {
  data: Record<string, number>;
  colors: Record<string, string>;
  total: number;
}) {
  if (total === 0) return null;
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full">
      {Object.entries(data).map(([key, count]) => (
        <div
          className={`${colors[key] ?? 'bg-slate-600'} transition-all`}
          key={key}
          style={{ width: `${(count / total) * 100}%` }}
          title={`${key}: ${count}`}
        />
      ))}
    </div>
  );
}

function StatCard({ stat }: { stat: ModelStat }) {
  const judgmentTotal = Object.values(stat.judgments).reduce((s, n) => s + n, 0);
  const outcomeTotal = Object.values(stat.outcomes).reduce((s, n) => s + n, 0);

  return (
    <div className="flex flex-col gap-5 rounded-xl border border-amber-100/10 bg-slate-950/60 p-6 shadow-lg shadow-slate-950/30">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-amber-300">
            {stat.model}
          </p>
          <p className="mt-1 text-sm text-slate-400">
            총 <span className="font-semibold text-slate-200">{stat.total.toLocaleString('ko-KR')}</span>개 분석
          </p>
        </div>
        <div className="text-right">
          <p className="text-3xl font-semibold tracking-tight text-slate-50">
            {ratio(stat.win_rate)}
          </p>
          <p className="mt-0.5 text-xs text-slate-500">승률 (매수)</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-lg border border-slate-800/80 bg-slate-900/60 px-4 py-3">
          <p className="text-xs text-slate-500">기대값</p>
          <p
            className={`mt-1 text-xl font-semibold ${
              stat.expectancy_pct === null
                ? 'text-slate-400'
                : stat.expectancy_pct >= 0
                  ? 'text-emerald-400'
                  : 'text-rose-400'
            }`}
          >
            {pct(stat.expectancy_pct)}
          </p>
        </div>
        <div className="rounded-lg border border-slate-800/80 bg-slate-900/60 px-4 py-3">
          <p className="text-xs text-slate-500">평균 보유</p>
          <p className="mt-1 text-xl font-semibold text-slate-200">
            {weeks(stat.avg_holding_weeks)}
          </p>
        </div>
      </div>

      <div className="space-y-3">
        <div>
          <div className="mb-1.5 flex justify-between text-xs text-slate-500">
            <span>판정 분포</span>
            <span className="flex gap-3">
              {Object.entries(stat.judgments).map(([key, count]) => (
                <span key={key}>
                  {key} {count}
                </span>
              ))}
            </span>
          </div>
          <MiniBar colors={JUDGMENT_COLORS} data={stat.judgments} total={judgmentTotal} />
        </div>

        {outcomeTotal > 0 && (
          <div>
            <div className="mb-1.5 flex justify-between text-xs text-slate-500">
              <span>결과 분포</span>
              <span className="flex gap-3">
                {Object.entries(stat.outcomes).map(([key, count]) => (
                  <span key={key}>
                    {key} {count}
                  </span>
                ))}
              </span>
            </div>
            <MiniBar colors={OUTCOME_COLORS} data={stat.outcomes} total={outcomeTotal} />
          </div>
        )}
      </div>
    </div>
  );
}

function LoadingGrid() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 3 }, (_, i) => (
        <div
          className="h-64 animate-pulse rounded-xl border border-amber-100/10 bg-slate-950/60"
          key={i}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section 2 — signal matrix heatmap
// ---------------------------------------------------------------------------

const CLOUD_POSITIONS = ['구름 위', '구름 안', '구름 아래'] as const;
const MA_ALIGNMENTS = ['정배열', '혼조', '역배열'] as const;

function HeatmapCell({ cell }: { cell: SignalCell | undefined }) {
  if (!cell) {
    return (
      <div
        className="flex flex-col items-center justify-center rounded-lg p-4 text-center"
        style={{ background: 'hsl(220, 10%, 10%)' }}
      >
        <span className="text-xs text-slate-700">—</span>
      </div>
    );
  }
  return (
    <div
      className="flex flex-col items-center justify-center gap-1 rounded-lg p-4 text-center transition-all"
      style={{ background: cellBg(cell.win_rate) }}
    >
      <span className="text-xs text-slate-400">
        n=<span className="font-semibold text-slate-200">{cell.count}</span>
      </span>
      <span className="text-sm font-semibold text-slate-50">{ratio(cell.win_rate)}</span>
      <span
        className={`text-xs font-semibold ${
          cell.expectancy_pct === null
            ? 'text-slate-500'
            : cell.expectancy_pct >= 0
              ? 'text-emerald-300'
              : 'text-rose-300'
        }`}
      >
        EV {pct(cell.expectancy_pct)}
      </span>
    </div>
  );
}

function SignalMatrixSection({
  models,
  selectedModel,
  onSelectModel,
  data,
  isLoading,
}: {
  models: string[];
  selectedModel: string;
  onSelectModel: (m: string) => void;
  data: SignalMatrixStat | undefined;
  isLoading: boolean;
}) {
  const cellMap = new Map<string, SignalCell>();
  if (data) {
    for (const c of data.cells) {
      cellMap.set(`${c.cloud_position}|${c.ma_alignment}`, c);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="border-b border-amber-100/10 pb-4">
        <p className="text-xs font-semibold uppercase tracking-[0.32em] text-amber-300">
          signal matrix
        </p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-50">
          신호 매트릭스
        </h2>
      </div>

      <div className="flex items-center gap-3">
        <span className="text-sm text-slate-400">모델 선택</span>
        {models.length > 0 ? (
          <select
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-amber-400/60"
            value={selectedModel}
            onChange={(e) => onSelectModel(e.target.value)}
          >
            {models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        ) : (
          <span className="text-sm text-slate-600">모델 없음</span>
        )}
      </div>

      {isLoading ? (
        <div className="h-48 animate-pulse rounded-xl border border-amber-100/10 bg-slate-950/60" />
      ) : !data || data.cells.length === 0 ? (
        <div className="rounded-lg border border-amber-100/10 bg-slate-950/45 px-6 py-10 text-center">
          <p className="text-sm text-slate-500">
            {!selectedModel ? '모델을 선택해 주세요.' : '분석 데이터가 없습니다.'}
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <div className="min-w-[480px]">
            {/* Column headers — ma_alignment */}
            <div className="mb-2 grid grid-cols-4 gap-2">
              <div /> {/* row header spacer */}
              {MA_ALIGNMENTS.map((ma) => (
                <div className="text-center text-xs font-semibold text-slate-400" key={ma}>
                  {ma}
                </div>
              ))}
            </div>
            {/* Rows — cloud_position */}
            {CLOUD_POSITIONS.map((cp) => (
              <div className="mb-2 grid grid-cols-4 gap-2" key={cp}>
                <div className="flex items-center text-xs font-semibold text-slate-400">{cp}</div>
                {MA_ALIGNMENTS.map((ma) => (
                  <HeatmapCell cell={cellMap.get(`${cp}|${ma}`)} key={ma} />
                ))}
              </div>
            ))}
            {/* Legend */}
            <div className="mt-3 flex items-center gap-3 text-xs text-slate-600">
              <div
                className="h-3 w-16 rounded-sm"
                style={{
                  background:
                    'linear-gradient(to right, hsl(0,55%,18%), hsl(40,55%,18%), hsl(120,55%,18%))',
                }}
              />
              <span>낮은 승률 → 높은 승률</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

function StatsPage() {
  const { data: stats = [], isError, isLoading, refetch } = useStatsByModel();

  const [selectedModel, setSelectedModel] = useState<string>('');

  useEffect(() => {
    if (stats.length > 0 && !selectedModel) {
      setSelectedModel(stats[0].model);
    }
  }, [stats, selectedModel]);

  const { data: signalData, isLoading: signalLoading } = useBySignal(selectedModel);

  const modelNames = stats.map((s) => s.model);

  return (
    <section className="flex flex-col gap-12">
      {/* Section 1: by-model */}
      <div className="flex flex-col gap-6">
        <div className="border-b border-amber-100/10 pb-4">
          <p className="text-xs font-semibold uppercase tracking-[0.32em] text-amber-300">
            performance stats
          </p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-50">
            모델별 통계
          </h2>
        </div>

        {isError ? (
          <div className="rounded-lg border border-rose-200/20 bg-rose-950/20 px-6 py-5">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-rose-100">통계를 불러오지 못했습니다.</p>
                <p className="mt-1 text-sm text-rose-100/70">
                  백엔드 응답 상태를 확인한 뒤 다시 시도하세요.
                </p>
              </div>
              <button
                className="rounded-md border border-rose-100/25 px-4 py-2 text-sm font-semibold text-rose-50 transition hover:bg-rose-100/10"
                onClick={() => void refetch()}
                type="button"
              >
                다시 시도
              </button>
            </div>
          </div>
        ) : isLoading ? (
          <LoadingGrid />
        ) : stats.length === 0 ? (
          <div className="rounded-lg border border-amber-100/10 bg-slate-950/45 px-6 py-12 text-center">
            <p className="text-sm font-semibold text-slate-100">아직 분석 데이터가 없습니다.</p>
            <p className="mt-2 text-sm text-slate-400">
              룰 스코어러나 LLM 분석을 실행한 뒤 다시 확인하세요.
            </p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {stats.map((stat) => (
              <StatCard key={stat.model} stat={stat} />
            ))}
          </div>
        )}
      </div>

      {/* Section 2: signal matrix */}
      <SignalMatrixSection
        data={signalData}
        isLoading={signalLoading}
        models={modelNames}
        onSelectModel={setSelectedModel}
        selectedModel={selectedModel}
      />
    </section>
  );
}

export default StatsPage;
