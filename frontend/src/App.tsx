import { NavLink, Navigate, Route, Routes } from 'react-router-dom';
import AnalysisDetailPage from './pages/AnalysisDetailPage';
import RunListPage from './pages/RunListPage';
import StockListPage from './pages/StockListPage';

const navItems = [
  { to: '/runs', label: 'Runs' },
  { to: '/analyses', label: 'Analyses' },
  { to: '/settings', label: 'Settings' },
];

const routePlaceholders = {
  analyses: {
    eyebrow: 'ai analysis',
    title: 'Analysis review workspace is ready.',
    description:
      'This route will render markdown-based stock analysis with GFM support.',
  },
  settings: {
    eyebrow: 'workspace',
    title: 'Personal workflow settings are ready.',
    description:
      'This route will hold local preferences for the focused trading journal.',
  },
} as const;

function PlaceholderRoute({
  route,
}: {
  route: keyof typeof routePlaceholders;
}) {
  const content = routePlaceholders[route];

  return (
    <section className="rounded-lg border border-amber-200/10 bg-slate-900/75 p-8 shadow-2xl shadow-slate-950/40">
      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-amber-300">
        {content.eyebrow}
      </p>
      <h2 className="mt-4 text-3xl font-semibold tracking-tight text-slate-50">
        {content.title}
      </h2>
      <p className="mt-3 max-w-2xl text-base leading-7 text-slate-300">
        {content.description}
      </p>
    </section>
  );
}

function App() {
  return (
    <main className="min-h-screen px-6 py-12 text-slate-50">
      <div className="mx-auto flex max-w-6xl flex-col gap-10">
        <header className="flex items-end justify-between gap-6 border-b border-amber-200/10 pb-6">
          <div className="space-y-3">
            <p className="text-sm font-semibold uppercase tracking-[0.35em] text-amber-300">
              greed
            </p>
            <h1 className="text-4xl font-semibold tracking-tight">
              Frontend workspace initialized.
            </h1>
            <p className="max-w-3xl text-base leading-7 text-slate-300">
              Vite, React, TypeScript, Tailwind CSS, React Router, Axios, React
              Markdown, Remark GFM, and TanStack Query are configured.
            </p>
          </div>

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
          <Route
            element={<PlaceholderRoute route="analyses" />}
            path="/analyses"
          />
          <Route
            element={<AnalysisDetailPage />}
            path="/analyses/:id"
          />
          <Route
            element={<PlaceholderRoute route="settings" />}
            path="/settings"
          />
          <Route element={<Navigate replace to="/runs" />} path="*" />
        </Routes>
      </div>
    </main>
  );
}

export default App;
