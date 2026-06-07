import type {
  BacktestRunDetail,
  DailyRallyCandidates,
  DailyRallyInsights,
} from '../api/backtest';
import { formatPriceByTicker } from '../utils/formatPrice';

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
                  <td className="px-3 py-3 font-semibold text-slate-200">{rule.rule_label}</td>
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
                      {visibleRules.join(', ')}
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
