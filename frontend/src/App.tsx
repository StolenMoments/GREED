import { NavLink, Navigate, Route, Routes } from 'react-router-dom';
import { RunListPage } from './pages/RunListPage';

const navItems = [
  { to: '/runs', label: '실행' },
  { to: '/analyses', label: '분석' },
  { to: '/settings', label: '설정' },
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

function RunDetailPlaceholder() {
  return (
    <section className="rounded-lg border border-amber-200/10 bg-slate-900/75 p-8 shadow-2xl shadow-slate-950/40">
      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-amber-300">
        run detail
      </p>
      <h2 className="mt-4 text-3xl font-semibold tracking-tight text-slate-50">
        종목 목록 페이지가 준비 중입니다.
      </h2>
      <p className="mt-3 max-w-2xl text-base leading-7 text-slate-300">
        실행 항목 클릭 시 상세 URL로 이동하는 흐름은 연결되어 있습니다.
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
              AI 기술적 분석 저널
            </h1>
            <p className="max-w-3xl text-base leading-7 text-slate-300">
              주간 실행과 종목별 분석 결과를 한 화면에서 빠르게 훑고
              필요한 상세 흐름으로 이어갑니다.
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
          <Route element={<RunDetailPlaceholder />} path="/runs/:runId" />
          <Route
            element={<PlaceholderRoute route="analyses" />}
            path="/analyses"
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
