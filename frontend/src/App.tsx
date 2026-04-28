import { NavLink, Navigate, Route, Routes } from 'react-router-dom';
import AnalysisDetailPage from './pages/AnalysisDetailPage';
import AnalysisListPage from './pages/AnalysisListPage';
import RunListPage from './pages/RunListPage';
import StockListPage from './pages/StockListPage';
import StockSummaryPage from './pages/StockSummaryPage';

const navItems = [
  { to: '/runs', label: 'Runs' },
  { to: '/analyses', label: 'Analyses' },
  { to: '/stocks', label: 'Stocks' },
];

function App() {
  return (
    <main className="min-h-screen px-6 py-8 text-slate-50">
      <div className="mx-auto flex max-w-7xl flex-col gap-8">
        <header className="flex items-center justify-between gap-6 border-b border-amber-200/10 pb-4">
          <NavLink
            aria-label="전체 분석 목록으로 이동"
            className="text-3xl font-semibold uppercase tracking-[0.35em] text-amber-300 transition hover:text-amber-200"
            to="/analyses"
          >
            greed
          </NavLink>

          <nav className="flex shrink-0 items-center gap-2 rounded-lg border border-slate-700/80 bg-slate-950/70 p-1">
            {navItems.map((item) => (
              <NavLink
                className={({ isActive }) =>
                  [
                    'rounded-md px-4 py-2 text-sm font-medium transition',
                    isActive
                      ? 'bg-amber-300 text-slate-950'
                      : 'text-slate-300 hover:bg-slate-800 hover:text-slate-50',
                  ].join(' ')
                }
                key={item.to}
                to={item.to}
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </header>

        <Routes>
          <Route element={<Navigate replace to="/runs" />} path="/" />
          <Route element={<RunListPage />} path="/runs" />
          <Route element={<StockListPage />} path="/runs/:runId" />
          <Route element={<AnalysisListPage />} path="/analyses" />
          <Route
            element={<AnalysisDetailPage />}
            path="/analyses/:id"
          />
          <Route element={<StockSummaryPage />} path="/stocks" />
          <Route element={<Navigate replace to="/runs" />} path="*" />
        </Routes>
      </div>
    </main>
  );
}

export default App;
