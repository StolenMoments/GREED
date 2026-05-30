import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import {
  createBacktestUniverseMember,
  deactivateBacktestUniverseMember,
  fetchBacktestUniverse,
  updateBacktestUniverseMember,
  type BacktestUniverseMember,
} from '../api/backtest';
import { searchTickers, type TickerSearchResult } from '../api/tickers';

function BacktestUniversePage() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<TickerSearchResult[]>([]);
  const [selected, setSelected] = useState<TickerSearchResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const searchRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const trimmedQuery = query.trim();

  const { data: members = [], isLoading } = useQuery({
    queryKey: ['backtest', 'universe', 'all'],
    queryFn: () => fetchBacktestUniverse(true),
  });

  const activeCount = members.filter((member) => member.active).length;
  const nextSortOrder = members.reduce((max, member) => Math.max(max, member.sort_order), -1) + 1;

  const invalidateUniverse = () => {
    void queryClient.invalidateQueries({ queryKey: ['backtest', 'universe'] });
  };

  const createMutation = useMutation({
    mutationFn: createBacktestUniverseMember,
    onSuccess: () => {
      invalidateUniverse();
      setQuery('');
      setSelected(null);
      setSuggestions([]);
      setError(null);
    },
    onError: () => setError('Could not add ticker. It may already exist in the universe.'),
  });

  const updateMutation = useMutation({
    mutationFn: ({ ticker, active }: { ticker: string; active: boolean }) =>
      updateBacktestUniverseMember(ticker, { active }),
    onSuccess: invalidateUniverse,
    onError: () => setError('Could not update ticker status.'),
  });

  const deleteMutation = useMutation({
    mutationFn: deactivateBacktestUniverseMember,
    onSuccess: invalidateUniverse,
    onError: () => setError('Could not deactivate ticker.'),
  });

  useEffect(() => {
    if (searchRef.current) clearTimeout(searchRef.current);
    setError(null);
    if (trimmedQuery.length < 1) {
      setSuggestions([]);
      return;
    }

    searchRef.current = setTimeout(() => {
      searchTickers(trimmedQuery)
        .then((results) => setSuggestions(results.filter((result) => result.market === 'KR')))
        .catch(() => setSuggestions([]));
    }, 200);

    return () => {
      if (searchRef.current) clearTimeout(searchRef.current);
    };
  }, [trimmedQuery]);

  function addSelected() {
    if (!selected) return;
    createMutation.mutate({
      ticker: selected.code,
      name: selected.name,
      sort_order: nextSortOrder,
    });
  }

  return (
    <section className="flex flex-col gap-8">
      <div className="border-b border-amber-100/10 pb-4">
        <p className="text-xs font-semibold uppercase tracking-[0.32em] text-amber-300">
          universe
        </p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-50">
          Backtest Ticker Universe
        </h2>
        <p className="mt-2 text-sm text-slate-400">
          Active {activeCount.toLocaleString('ko-KR')} / total {members.length.toLocaleString('ko-KR')}
        </p>
      </div>

      <section className="rounded-lg border border-slate-800/80 bg-slate-950/55 p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.32em] text-amber-300">
              manage
            </p>
            <h3 className="mt-2 text-xl font-semibold tracking-tight text-slate-50">
              Target tickers
            </h3>
          </div>

          <div className="w-full max-w-xl">
            <div className="flex gap-2">
              <input
                className="min-h-11 min-w-0 flex-1 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm font-semibold text-slate-100 transition focus:outline-none focus:ring-2 focus:ring-amber-300/70"
                onChange={(event) => {
                  setSelected(null);
                  setQuery(event.target.value);
                }}
                placeholder="Search ticker or name"
                value={query}
              />
              <button
                className="min-h-11 rounded-md bg-amber-300 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-amber-200 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={!selected || createMutation.isPending}
                onClick={addSelected}
                type="button"
              >
                Add
              </button>
            </div>

            {suggestions.length > 0 && (
              <div className="mt-2 max-h-52 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950">
                {suggestions.map((suggestion) => (
                  <button
                    className={[
                      'flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left text-sm transition',
                      selected?.code === suggestion.code
                        ? 'bg-amber-300/10 text-amber-100'
                        : 'text-slate-300 hover:bg-slate-900',
                    ].join(' ')}
                    key={suggestion.code}
                    onClick={() => {
                      setSelected(suggestion);
                      setQuery(`${suggestion.code} ${suggestion.name}`);
                      setSuggestions([]);
                    }}
                    type="button"
                  >
                    <span className="truncate font-semibold">{suggestion.name}</span>
                    <span className="shrink-0 tabular-nums text-slate-500">{suggestion.code}</span>
                  </button>
                ))}
              </div>
            )}

            {error && <p className="mt-2 text-sm text-rose-200">{error}</p>}
          </div>
        </div>

        <div className="mt-5 overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-slate-500">
                <th className="px-3 py-2 text-left">Ticker</th>
                <th className="px-3 py-2 text-left">Name</th>
                <th className="px-3 py-2 text-right">Order</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td className="px-3 py-6 text-center text-slate-500" colSpan={5}>
                    Loading universe...
                  </td>
                </tr>
              ) : members.length === 0 ? (
                <tr>
                  <td className="px-3 py-6 text-center text-slate-500" colSpan={5}>
                    No universe members yet.
                  </td>
                </tr>
              ) : (
                members.map((member: BacktestUniverseMember) => (
                  <tr className="border-b border-slate-900/80" key={member.ticker}>
                    <td className="px-3 py-3 font-semibold tabular-nums text-slate-100">
                      {member.ticker}
                    </td>
                    <td className="px-3 py-3 text-slate-300">{member.name}</td>
                    <td className="px-3 py-3 text-right tabular-nums text-slate-500">
                      {member.sort_order}
                    </td>
                    <td className="px-3 py-3">
                      <span
                        className={[
                          'rounded-full border px-2.5 py-1 text-xs font-semibold',
                          member.active
                            ? 'border-emerald-200/25 bg-emerald-950/30 text-emerald-200'
                            : 'border-slate-700 bg-slate-900 text-slate-500',
                        ].join(' ')}
                      >
                        {member.active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-right">
                      {member.active ? (
                        <button
                          className="rounded-md border border-rose-200/25 px-3 py-1.5 text-xs font-semibold text-rose-100 transition hover:bg-rose-950/30"
                          disabled={deleteMutation.isPending}
                          onClick={() => deleteMutation.mutate(member.ticker)}
                          type="button"
                        >
                          Deactivate
                        </button>
                      ) : (
                        <button
                          className="rounded-md border border-emerald-200/25 px-3 py-1.5 text-xs font-semibold text-emerald-100 transition hover:bg-emerald-950/30"
                          disabled={updateMutation.isPending}
                          onClick={() => updateMutation.mutate({ ticker: member.ticker, active: true })}
                          type="button"
                        >
                          Reactivate
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}

export default BacktestUniversePage;
