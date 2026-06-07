import type {
  BacktestRunDetail,
  DailyRallyCandidate,
  DailyRallyCandidates,
  DailyRallyInsights,
  DailyRallyRuleStat,
} from '../api/backtest';
import { formatPriceByTicker } from '../utils/formatPrice';
import {
  classifyDailyRallyRule,
  explainDailyRallyRule,
  translateDailyRallyRule,
} from './dailyRallyInterpretation';

function ratio(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return '--';
  return `${(value * 100).toFixed(digits)}%`;
}

function count(value: number | null | undefined): string {
  if (value === null || value === undefined) return '--';
  return value.toLocaleString('ko-KR');
}

function date(value: string | null | undefined): string {
  if (!value) return '--';
  return new Date(value).toLocaleDateString('ko-KR');
}

function decimal(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return '--';
  return value.toFixed(digits);
}

function signedPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return '--';
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(digits)}%`;
}

function PanelShell({
  children,
  title,
}: {
  children: React.ReactNode;
  title: string;
}) {
  return (
    <div className="rounded-lg border border-slate-800/80 bg-slate-950/55 p-5">
      <div className="border-b border-amber-100/10 pb-3">
        <p className="text-xs font-semibold uppercase tracking-[0.32em] text-amber-300">
          {title}
        </p>
      </div>
      {children}
    </div>
  );
}

function LoadingBlock() {
  return (
    <div className="h-24 animate-pulse rounded-lg border border-amber-100/10 bg-slate-950/60" />
  );
}

export function DailyRallySummaryPanel({
  candidates,
  detail,
  insights,
  isLoading,
}: {
  candidates: DailyRallyCandidates | undefined;
  detail: BacktestRunDetail;
  insights: DailyRallyInsights | undefined;
  isLoading: boolean;
}) {
  if (isLoading) {
    return <LoadingBlock />;
  }

  const items = [
    { label: 'run', value: `#${detail.id}` },
    { label: 'signals', value: count(detail.signal_count) },
    { label: 'tickers', value: count(detail.ticker_count) },
    { label: 'data range', value: `${date(detail.data_start)} ~ ${date(detail.data_end)}` },
    { label: 'rules', value: count(insights?.rule_count) },
    { label: 'candidates', value: count(candidates?.candidate_count) },
  ];

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
      {items.map((item) => (
        <div
          className="rounded-lg border border-slate-800/80 bg-slate-950/60 px-5 py-4"
          key={item.label}
        >
          <p className="text-xs text-slate-500">{item.label}</p>
          <p className="mt-1 truncate text-2xl font-semibold text-slate-50">{item.value}</p>
        </div>
      ))}
    </div>
  );
}

function ruleStrengthTone(rule: DailyRallyRuleStat): string {
  if (rule.lift >= 3) return 'border-amber-200/40 bg-amber-300/10 text-amber-100';
  if (rule.lift >= 2) return 'border-emerald-200/30 bg-emerald-300/10 text-emerald-100';
  return 'border-slate-700 bg-slate-900/80 text-slate-300';
}

export function DailyRallyPatternBriefing({
  insights,
  isError,
}: {
  insights: DailyRallyInsights | undefined;
  isError: boolean;
}) {
  const topRules = insights?.rules.slice(0, 3) ?? [];

  return (
    <PanelShell title="pattern briefing">
      {isError ? (
        <p className="mt-4 text-sm font-semibold text-rose-200">
          패턴 요약을 불러오지 못했습니다.
        </p>
      ) : topRules.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">
          아직 반복 패턴으로 볼 만한 룰이 없습니다.
        </p>
      ) : (
        <div className="mt-5 grid gap-4">
          {topRules.map((rule, index) => (
            <article
              className="rounded-lg border border-slate-800 bg-slate-950/70 p-5"
              key={rule.id}
            >
              <div className="flex flex-wrap items-center gap-3">
                <span className="rounded-md bg-amber-300 px-2.5 py-1 text-xs font-bold text-slate-950">
                  #{index + 1}
                </span>
                <span
                  className={`rounded-md border px-2.5 py-1 text-xs font-semibold ${ruleStrengthTone(
                    rule,
                  )}`}
                >
                  {classifyDailyRallyRule(rule)}
                </span>
                <span className="text-xs text-slate-500">
                  lift {decimal(rule.lift)} · score {decimal(rule.score)}
                </span>
              </div>
              <h3 className="mt-4 text-xl font-semibold leading-snug text-slate-50">
                {translateDailyRallyRule(rule.rule_key)}
              </h3>
              <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-300">
                {explainDailyRallyRule(rule)}
              </p>
            </article>
          ))}
        </div>
      )}
    </PanelShell>
  );
}

function candidateReason(candidate: DailyRallyCandidate): string {
  if (candidate.matched_rules.length === 0) {
    return '매칭된 패턴이 없습니다.';
  }
  return candidate.matched_rules
    .slice(0, 2)
    .map(translateDailyRallyRule)
    .join(' / ');
}

export function DailyRallyCandidateBriefing({
  candidates,
  isError,
}: {
  candidates: DailyRallyCandidates | undefined;
  isError: boolean;
}) {
  const topCandidates = candidates?.candidates.slice(0, 8) ?? [];

  return (
    <PanelShell title="candidate briefing">
      {isError ? (
        <p className="mt-4 text-sm font-semibold text-rose-200">
          후보 요약을 불러오지 못했습니다.
        </p>
      ) : topCandidates.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">
          현재 데이터 기준으로 매칭된 후보가 없습니다.
        </p>
      ) : (
        <div className="mt-5 grid gap-3 xl:grid-cols-2">
          {topCandidates.map((candidate) => (
            <article
              className="rounded-lg border border-slate-800 bg-slate-950/65 p-4"
              key={candidate.id}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-lg font-semibold text-slate-50">
                    {candidate.name}
                    <span className="ml-2 text-sm text-amber-200">{candidate.ticker}</span>
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {date(candidate.signal_date)} · {formatPriceByTicker(
                      candidate.close_price,
                      candidate.ticker,
                    ) ?? count(candidate.close_price)}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-xs text-slate-500">max score</p>
                  <p className="text-lg font-semibold text-amber-200">
                    {decimal(candidate.max_rule_score)}
                  </p>
                </div>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-300">
                {candidateReason(candidate)}
              </p>
              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                <span className="rounded-md border border-slate-700 px-2 py-1 text-slate-300">
                  매칭 룰 {count(candidate.matched_rule_count)}개
                </span>
                {typeof candidate.features.ret_20d === 'number' && (
                  <span className="rounded-md border border-slate-700 px-2 py-1 text-slate-300">
                    20일 {signedPct(candidate.features.ret_20d)}
                  </span>
                )}
                {typeof candidate.features.volume_ratio_20d === 'number' && (
                  <span className="rounded-md border border-slate-700 px-2 py-1 text-slate-300">
                    거래량 {decimal(candidate.features.volume_ratio_20d)}배
                  </span>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </PanelShell>
  );
}

export function DailyRallyRulesTable({
  insights,
  isError,
}: {
  insights: DailyRallyInsights | undefined;
  isError: boolean;
}) {
  return (
    <PanelShell title="rule insights">
      {isError ? (
        <p className="mt-4 text-sm font-semibold text-rose-200">
          Could not load daily rally rule insights.
        </p>
      ) : !insights || insights.rules.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">No mined rules for this run.</p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-sm">
            <thead>
              <tr className="text-slate-400">
                <th className="px-3 py-2 text-left">Rule</th>
                <th className="px-3 py-2 text-right">Support</th>
                <th className="px-3 py-2 text-right">Precision</th>
                <th className="px-3 py-2 text-right">Base Rate</th>
                <th className="px-3 py-2 text-right">Lift</th>
                <th className="px-3 py-2 text-right">Score</th>
              </tr>
            </thead>
            <tbody>
              {insights.rules.map((rule) => (
                <tr className="border-t border-slate-800/70" key={rule.id}>
                  <td className="px-3 py-3">
                    <p className="font-semibold text-slate-200">
                      {translateDailyRallyRule(rule.rule_key)}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">{rule.rule_label}</p>
                  </td>
                  <td className="px-3 py-3 text-right text-slate-300">
                    {count(rule.support)}
                  </td>
                  <td className="px-3 py-3 text-right font-semibold text-emerald-300">
                    {ratio(rule.precision)}
                  </td>
                  <td className="px-3 py-3 text-right text-slate-300">
                    {ratio(rule.base_rate)}
                  </td>
                  <td className="px-3 py-3 text-right text-slate-300">
                    {decimal(rule.lift)}
                  </td>
                  <td className="px-3 py-3 text-right font-semibold text-amber-200">
                    {decimal(rule.score)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PanelShell>
  );
}

export function DailyRallyCandidatesTable({
  candidates,
  isError,
}: {
  candidates: DailyRallyCandidates | undefined;
  isError: boolean;
}) {
  return (
    <PanelShell title="current candidates">
      {isError ? (
        <p className="mt-4 text-sm font-semibold text-rose-200">
          Could not load daily rally current candidates.
        </p>
      ) : !candidates || candidates.candidates.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">No current candidates for this run.</p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[860px] border-collapse text-sm">
            <thead>
              <tr className="text-slate-400">
                <th className="px-3 py-2 text-left">Ticker</th>
                <th className="px-3 py-2 text-left">Name</th>
                <th className="px-3 py-2 text-right">Signal Date</th>
                <th className="px-3 py-2 text-right">Close</th>
                <th className="px-3 py-2 text-left">Matched Rules</th>
                <th className="px-3 py-2 text-right">Max Score</th>
                <th className="px-3 py-2 text-right">Mean Score</th>
              </tr>
            </thead>
            <tbody>
              {candidates.candidates.map((candidate) => {
                const visibleRules = candidate.matched_rules.slice(0, 3);
                const hiddenRuleCount = candidate.matched_rules.length - visibleRules.length;
                return (
                  <tr className="border-t border-slate-800/70" key={candidate.id}>
                    <td className="px-3 py-3 font-semibold text-amber-100">
                      {candidate.ticker}
                    </td>
                    <td className="px-3 py-3 text-slate-200">{candidate.name}</td>
                    <td className="px-3 py-3 text-right text-slate-300">
                      {date(candidate.signal_date)}
                    </td>
                    <td className="px-3 py-3 text-right text-slate-300">
                      {formatPriceByTicker(candidate.close_price, candidate.ticker) ??
                        count(candidate.close_price)}
                    </td>
                    <td className="px-3 py-3 text-slate-300">
                      {visibleRules.map(translateDailyRallyRule).join(', ')}
                      {hiddenRuleCount > 0 ? ` +${hiddenRuleCount}` : ''}
                    </td>
                    <td className="px-3 py-3 text-right font-semibold text-amber-200">
                      {decimal(candidate.max_rule_score)}
                    </td>
                    <td className="px-3 py-3 text-right text-slate-300">
                      {decimal(candidate.mean_rule_score)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </PanelShell>
  );
}
