# Backtest Jobs Page Design

## Goal

Show analysis backtest jobs on the existing Jobs page so the operator can see whether background backtests are still running or have failed.

## Scope

- Keep the current Jobs page layout and visual structure.
- Add backtest jobs to the same operational list used for ticker analysis jobs.
- Prioritize active and failed states: `pending`, `running`, and `failed`.
- Do not change how analysis jobs or backtest jobs are executed.
- Do not add a separate backtest jobs page.

## Recommended Approach

Add a Jobs-page-specific backend read endpoint that returns a unified list of job rows. This avoids changing the existing `/api/jobs` contract, which is currently specific to ticker analysis jobs, and avoids inefficient frontend fan-out across every analysis detail endpoint.

## Backend Design

Create `GET /api/jobs/overview`.

The endpoint reads from:

- `analysis_jobs`
- `analysis_backtest_jobs`, joined to `analyses` for ticker/run context

Each row includes:

- `kind`: `analysis` or `analysis_backtest`
- `id`
- `status`
- `ticker`
- `run_id`
- `model`
- `created_at`
- `error_message`
- optional `analysis_id`
- optional `backtest_run_id`
- optional `similarity_threshold`

The endpoint accepts repeated `status` query parameters. Valid statuses are `pending`, `running`, `done`, and `failed`; analysis jobs only produce `pending`, `done`, and `failed`.

## Frontend Design

Update `JobsPage` to consume the unified overview endpoint while preserving its existing table-like layout.

Display rules:

- Analysis rows keep their current behavior.
- Backtest rows show the source analysis ticker in the `ticker` column.
- Backtest rows show `similarity >= N` in the `model` column.
- Backtest rows link to `Backtest #id` when `backtest_run_id` is present.
- Backtest failed rows show `error_message` in the detail column.
- Active counts include both `pending` and `running`.

## Testing

Backend tests cover:

- The overview endpoint includes pending/failed analysis and analysis-backtest jobs.
- Status filtering supports `running`.
- Backtest rows include source ticker, run id, analysis id, threshold, and error message.

Frontend verification covers:

- TypeScript build succeeds.
- Jobs page can render unified rows without changing the visible layout structure.
