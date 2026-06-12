import type {
  BacktestRunDetail,
  DailyRallyCandidate,
  DailyRallyCandidates,
  DailyRallyInsights,
  DailyRallyPatternStat,
  DailyRallyPatternStats,
  DailyRallyRuleStat,
  DailyRallyValidation,
} from '../api/backtest';
import React from 'react';
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

function DailyRallyStrictRulePatternBriefing({
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

function patternReturnMean(pattern: DailyRallyPatternStat, horizon: number): number | null {
  return pattern.return_stats.find((stat) => stat.horizon === horizon)?.mean ?? null;
}

function patternStrengthTone(pattern: DailyRallyPatternStat): string {
  if (pattern.lift >= 3) return 'border-amber-200/40 bg-amber-300/10 text-amber-100';
  if (pattern.lift >= 2) return 'border-emerald-200/30 bg-emerald-300/10 text-emerald-100';
  return 'border-slate-700 bg-slate-900/80 text-slate-300';
}

export function DailyRallyPatternBriefing({
  insights,
  isError,
  patternStats,
  patternStatsIsError = false,
}: {
  insights: DailyRallyInsights | undefined;
  isError: boolean;
  patternStats?: DailyRallyPatternStats;
  patternStatsIsError?: boolean;
}) {
  const topRules = insights?.rules.slice(0, 3) ?? [];
  const topPatterns = patternStats?.patterns.slice(0, 3) ?? [];

  if (topRules.length > 0 || isError) {
    return <DailyRallyStrictRulePatternBriefing insights={insights} isError={isError} />;
  }

  return (
    <PanelShell title="pattern briefing">
      {patternStatsIsError ? (
        <p className="mt-4 text-sm font-semibold text-rose-200">
          Could not load daily rally pattern stats.
        </p>
      ) : topPatterns.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">
          No strict rules yet. Check Pattern Stats after the next Daily Rally run.
        </p>
      ) : (
        <div className="mt-5 grid gap-4">
          {topPatterns.map((pattern, index) => (
            <article
              className="rounded-lg border border-slate-800 bg-slate-950/70 p-5"
              key={pattern.id}
            >
              <div className="flex flex-wrap items-center gap-3">
                <span className="rounded-md bg-amber-300 px-2.5 py-1 text-xs font-bold text-slate-950">
                  #{index + 1}
                </span>
                <span
                  className={`rounded-md border px-2.5 py-1 text-xs font-semibold ${patternStrengthTone(
                    pattern,
                  )}`}
                >
                  Exploratory pattern
                </span>
                <span className="text-xs text-slate-500">
                  lift {decimal(pattern.lift)} 쨌 score {decimal(pattern.score)}
                </span>
              </div>
              <h3 className="mt-4 text-xl font-semibold leading-snug text-slate-50">
                {translateDailyRallyRule(pattern.pattern_key)}
              </h3>
              <p className="mt-1 text-xs text-slate-500">{pattern.pattern_label}</p>
              <p className="mt-3 max-w-4xl text-sm leading-6 text-slate-300">
                Matches {count(pattern.total_matches)} samples, with {count(pattern.support)} positive events.
                Precision {ratio(pattern.precision)} versus base rate {ratio(pattern.base_rate)}.
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
          No strict-rule candidates right now. Use Pattern Stats to inspect exploratory conditions.
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
                  <p className="text-xs text-slate-500">
                    {candidate.composite_score === null ? 'max score' : 'composite'}
                  </p>
                  <p className="text-lg font-semibold text-amber-200">
                    {candidate.composite_score === null
                      ? decimal(candidate.max_rule_score)
                      : decimal(candidate.composite_score, 1)}
                  </p>
                </div>
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-300">
                {candidateReason(candidate)}
              </p>
              <div className="mt-3 flex flex-wrap gap-2 text-xs">
                {candidate.stability_classification !== null && (
                  <span
                    className={`rounded-md border border-slate-700 px-2 py-1 font-semibold ${validationTone(
                      candidate.stability_classification,
                    )}`}
                  >
                    {stabilityLabel(candidate.stability_classification)}
                  </span>
                )}
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

export function DailyRallyPatternStatsTable({
  patternStats,
  isError,
}: {
  patternStats: DailyRallyPatternStats | undefined;
  isError: boolean;
}) {
  return (
    <PanelShell title="Pattern Stats">
      {isError ? (
        <p className="mt-4 text-sm font-semibold text-rose-200">
          Could not load daily rally pattern stats.
        </p>
      ) : !patternStats || patternStats.patterns.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">No pattern stats for this run.</p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[980px] border-collapse text-sm">
            <thead>
              <tr className="text-slate-400">
                <th className="px-3 py-2 text-left">Pattern</th>
                <th className="px-3 py-2 text-right">Support</th>
                <th className="px-3 py-2 text-right">Matches</th>
                <th className="px-3 py-2 text-right">Precision</th>
                <th className="px-3 py-2 text-right">Base Rate</th>
                <th className="px-3 py-2 text-right">Lift</th>
                <th className="px-3 py-2 text-right">20d Mean</th>
                <th className="px-3 py-2 text-right">40d Mean</th>
                <th className="px-3 py-2 text-right">60d Mean</th>
                <th className="px-3 py-2 text-right">120d Mean</th>
              </tr>
            </thead>
            <tbody>
              {patternStats.patterns.map((pattern) => (
                <tr className="border-t border-slate-800/70" key={pattern.id}>
                  <td className="px-3 py-3">
                    <p className="font-semibold text-slate-200">
                      {translateDailyRallyRule(pattern.pattern_key)}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">{pattern.pattern_label}</p>
                  </td>
                  <td className="px-3 py-3 text-right text-slate-300">
                    {count(pattern.support)}
                  </td>
                  <td className="px-3 py-3 text-right text-slate-300">
                    {count(pattern.total_matches)}
                  </td>
                  <td className="px-3 py-3 text-right font-semibold text-emerald-300">
                    {ratio(pattern.precision)}
                  </td>
                  <td className="px-3 py-3 text-right text-slate-300">
                    {ratio(pattern.base_rate)}
                  </td>
                  <td className="px-3 py-3 text-right text-slate-300">
                    {decimal(pattern.lift)}
                  </td>
                  {[20, 40, 60, 120].map((horizon) => (
                    <td
                      className="px-3 py-3 text-right font-semibold text-slate-200"
                      key={`${pattern.id}:${horizon}`}
                    >
                      {signedPct(patternReturnMean(pattern, horizon))}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PanelShell>
  );
}

function summaryNumber(summary: Record<string, unknown>, key: string): number | null {
  const value = summary[key];
  return typeof value === 'number' ? value : null;
}

function summaryYears(summary: Record<string, unknown>, key: string): number[] {
  const value = summary[key];
  return Array.isArray(value) ? value.filter((item): item is number => typeof item === 'number') : [];
}

function validationTone(classification: string): string {
  if (classification === 'stable') return 'text-emerald-300';
  if (classification === 'fragile') return 'text-amber-200';
  return 'text-slate-400';
}

function stabilityLabel(classification: string | null | undefined): string {
  if (classification === 'stable') return '안정';
  if (classification === 'fragile') return '불안정';
  if (classification === 'insufficient') return '검증부족';
  return '—';
}

export function DailyRallyValidationPanel({
  validation,
  isError,
}: {
  validation: DailyRallyValidation | undefined;
  isError: boolean;
}) {
  if (isError) {
    return (
      <PanelShell title="Validation">
        <p className="mt-4 text-sm font-semibold text-rose-200">
          Could not load daily rally validation.
        </p>
      </PanelShell>
    );
  }

  if (!validation) {
    return (
      <PanelShell title="Validation">
        <p className="mt-4 text-sm text-slate-500">No validation summary for this run.</p>
      </PanelShell>
    );
  }

  const completeYears = summaryYears(validation.summary, 'complete_years');
  const partialYears = summaryYears(validation.summary, 'partial_years');
  const validationRange =
    completeYears.length > 0 ? `${completeYears[0]} ~ ${completeYears[completeYears.length - 1]}` : '--';
  const topShare = summaryNumber(validation.summary, 'top_positive_ticker_share');
  const walkForwardMedianLift = summaryNumber(validation.summary, 'walk_forward_median_lift');

  return (
    <PanelShell title="Validation">
      <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: 'validation years', value: validationRange },
          { label: 'partial year', value: partialYears.length ? partialYears.join(', ') : '--' },
          { label: 'positive concentration', value: ratio(topShare) },
          { label: 'walk-forward median lift', value: decimal(walkForwardMedianLift) },
        ].map((item) => (
          <div
            className="rounded-lg border border-slate-800/80 bg-slate-950/60 px-4 py-3"
            key={item.label}
          >
            <p className="text-xs text-slate-500">{item.label}</p>
            <p className="mt-1 text-xl font-semibold text-slate-50">{item.value}</p>
          </div>
        ))}
      </div>

      {validation.warnings.length > 0 && (
        <div className="mt-4 rounded-lg border border-amber-200/20 bg-amber-300/10 px-4 py-3">
          {validation.warnings.map((warning) => (
            <p className="text-sm text-amber-100" key={warning}>
              {warning}
            </p>
          ))}
        </div>
      )}

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] border-collapse text-sm">
            <thead>
              <tr className="text-slate-400">
                <th className="px-3 py-2 text-left">Year</th>
                <th className="px-3 py-2 text-right">Total</th>
                <th className="px-3 py-2 text-right">Positives</th>
                <th className="px-3 py-2 text-right">Base Rate</th>
                <th className="px-3 py-2 text-right">Positive 120d</th>
              </tr>
            </thead>
            <tbody>
              {validation.year_breakdown.map((item) => (
                <tr className="border-t border-slate-800/70" key={item.year}>
                  <td className="px-3 py-3 font-semibold text-slate-200">
                    {item.year}
                    {item.partial ? <span className="ml-2 text-xs text-amber-200">partial</span> : null}
                  </td>
                  <td className="px-3 py-3 text-right text-slate-300">{count(item.total)}</td>
                  <td className="px-3 py-3 text-right text-slate-300">{count(item.positives)}</td>
                  <td className="px-3 py-3 text-right text-slate-300">{ratio(item.base_rate)}</td>
                  <td className="px-3 py-3 text-right font-semibold text-slate-200">
                    {signedPct(item.positive_forward_return_120d_mean)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] border-collapse text-sm">
            <thead>
              <tr className="text-slate-400">
                <th className="px-3 py-2 text-left">Ticker</th>
                <th className="px-3 py-2 text-left">Name</th>
                <th className="px-3 py-2 text-right">Positives</th>
                <th className="px-3 py-2 text-right">Share</th>
              </tr>
            </thead>
            <tbody>
              {validation.ticker_concentration.slice(0, 8).map((item) => (
                <tr className="border-t border-slate-800/70" key={item.ticker}>
                  <td className="px-3 py-3 font-semibold text-amber-100">{item.ticker}</td>
                  <td className="px-3 py-3 text-slate-200">{item.name}</td>
                  <td className="px-3 py-3 text-right text-slate-300">
                    {count(item.positive_count)}
                  </td>
                  <td className="px-3 py-3 text-right text-slate-300">
                    {ratio(item.positive_share)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[900px] border-collapse text-sm">
          <thead>
            <tr className="text-slate-400">
              <th className="px-3 py-2 text-left">Pattern</th>
              <th className="px-3 py-2 text-right">Full Lift</th>
              <th className="px-3 py-2 text-right">Test Windows</th>
              <th className="px-3 py-2 text-right">Median Test Lift</th>
              <th className="px-3 py-2 text-right">Lift &gt; 1</th>
              <th className="px-3 py-2 text-right">Status</th>
            </tr>
          </thead>
          <tbody>
            {validation.pattern_stability.slice(0, 12).map((item) => (
              <tr className="border-t border-slate-800/70" key={item.pattern_key}>
                <td className="px-3 py-3">
                  <p className="font-semibold text-slate-200">
                    {translateDailyRallyRule(item.pattern_key)}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">{item.pattern_label}</p>
                </td>
                <td className="px-3 py-3 text-right text-slate-300">
                  {decimal(item.full_period_lift)}
                </td>
                <td className="px-3 py-3 text-right text-slate-300">
                  {count(item.test_window_count)}
                </td>
                <td className="px-3 py-3 text-right font-semibold text-slate-200">
                  {decimal(item.median_test_lift)}
                </td>
                <td className="px-3 py-3 text-right text-slate-300">
                  {ratio(item.test_lift_gt_1_ratio)}
                </td>
                <td className={`px-3 py-3 text-right font-semibold ${validationTone(item.classification)}`}>
                  {item.classification}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[940px] border-collapse text-sm">
          <thead>
            <tr className="text-slate-400">
              <th className="px-3 py-2 text-left">Window</th>
              <th className="px-3 py-2 text-left">Top Pattern</th>
              <th className="px-3 py-2 text-right">Train Lift</th>
              <th className="px-3 py-2 text-right">Test Matches</th>
              <th className="px-3 py-2 text-right">Test Precision</th>
              <th className="px-3 py-2 text-right">Test Lift</th>
            </tr>
          </thead>
          <tbody>
            {validation.walk_forward_windows.map((item) => (
              <tr className="border-t border-slate-800/70" key={`${item.train_years.join('-')}:${item.test_year}`}>
                <td className="px-3 py-3 font-semibold text-slate-200">
                  {item.train_years.join('-')} &gt; {item.test_year}
                </td>
                <td className="px-3 py-3 text-slate-300">
                  {item.pattern_key ? translateDailyRallyRule(item.pattern_key) : '--'}
                </td>
                <td className="px-3 py-3 text-right text-slate-300">
                  {decimal(item.train_lift)}
                </td>
                <td className="px-3 py-3 text-right text-slate-300">
                  {count(item.test_matches)}
                </td>
                <td className="px-3 py-3 text-right text-slate-300">
                  {ratio(item.test_precision)}
                </td>
                <td className="px-3 py-3 text-right font-semibold text-slate-200">
                  {decimal(item.test_lift)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
  const [expandedId, setExpandedId] = React.useState<number | null>(null);

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
          <table className="w-full min-w-[980px] border-collapse text-sm">
            <thead>
              <tr className="text-slate-400">
                <th className="px-3 py-2 text-right">#</th>
                <th className="px-3 py-2 text-left">Ticker</th>
                <th className="px-3 py-2 text-left">Name</th>
                <th className="px-3 py-2 text-right">Signal Date</th>
                <th className="px-3 py-2 text-right">Close</th>
                <th className="px-3 py-2 text-left">Matched Rules</th>
                <th className="px-3 py-2 text-right">Composite</th>
                <th className="px-3 py-2 text-right">Stability</th>
                <th className="px-3 py-2 text-right">Max Score</th>
              </tr>
            </thead>
            <tbody>
              {candidates.candidates.map((candidate, index) => {
                const visibleRules = candidate.matched_rules.slice(0, 3);
                const hiddenRuleCount = candidate.matched_rules.length - visibleRules.length;
                const hasBreakdown = candidate.rule_breakdowns.length > 0;
                const isExpanded = expandedId === candidate.id;
                return (
                  <React.Fragment key={candidate.id}>
                    <tr className="border-t border-slate-800/70">
                      <td className="px-3 py-3 text-right text-slate-500">{index + 1}</td>
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
                        {candidate.composite_score === null ? (
                          '—'
                        ) : hasBreakdown ? (
                          <button
                            className="font-semibold text-amber-200 underline decoration-amber-200/40 underline-offset-4 hover:decoration-amber-200"
                            onClick={() =>
                              setExpandedId(isExpanded ? null : candidate.id)
                            }
                            type="button"
                          >
                            {decimal(candidate.composite_score, 1)}
                          </button>
                        ) : (
                          decimal(candidate.composite_score, 1)
                        )}
                      </td>
                      <td
                        className={`px-3 py-3 text-right font-semibold ${validationTone(
                          candidate.stability_classification ?? '',
                        )}`}
                      >
                        {stabilityLabel(candidate.stability_classification)}
                      </td>
                      <td className="px-3 py-3 text-right text-slate-300">
                        {decimal(candidate.max_rule_score)}
                      </td>
                    </tr>
                    {isExpanded && hasBreakdown && (
                      <tr className="border-t border-slate-800/40 bg-slate-950/45">
                        <td className="px-3 py-3" colSpan={9}>
                          <table className="w-full border-collapse text-xs">
                            <thead>
                              <tr className="text-slate-500">
                                <th className="px-2 py-1 text-left">Rule</th>
                                <th className="px-2 py-1 text-right">Quality</th>
                                <th className="px-2 py-1 text-right">Stability</th>
                                <th className="px-2 py-1 text-right">Exp. Return</th>
                                <th className="px-2 py-1 text-right">20d Win</th>
                                <th className="px-2 py-1 text-right">20d Median</th>
                                <th className="px-2 py-1 text-right">Composite</th>
                              </tr>
                            </thead>
                            <tbody>
                              {candidate.rule_breakdowns.map((breakdown) => (
                                <tr
                                  className="border-t border-slate-800/40"
                                  key={breakdown.rule_key}
                                >
                                  <td className="px-2 py-2 text-slate-300">
                                    {translateDailyRallyRule(breakdown.rule_key)}
                                  </td>
                                  <td className="px-2 py-2 text-right text-slate-300">
                                    {decimal(breakdown.rule_quality)}
                                  </td>
                                  <td
                                    className={`px-2 py-2 text-right ${validationTone(
                                      breakdown.stability_classification,
                                    )}`}
                                  >
                                    {stabilityLabel(breakdown.stability_classification)} ×
                                    {decimal(breakdown.stability_multiplier, 1)}
                                  </td>
                                  <td className="px-2 py-2 text-right text-slate-300">
                                    {decimal(breakdown.expected_return)}
                                  </td>
                                  <td className="px-2 py-2 text-right text-slate-300">
                                    {ratio(breakdown.win_rate_20d)}
                                  </td>
                                  <td className="px-2 py-2 text-right text-slate-300">
                                    {signedPct(breakdown.median_return_20d)}
                                  </td>
                                  <td className="px-2 py-2 text-right font-semibold text-amber-200">
                                    {decimal(breakdown.rule_composite, 1)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </PanelShell>
  );
}
