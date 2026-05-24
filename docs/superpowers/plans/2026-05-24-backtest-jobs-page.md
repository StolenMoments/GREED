# Backtest Jobs Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add analysis backtest jobs to the existing Jobs page so active and failed background backtests are visible alongside ticker analysis jobs.

**Architecture:** Add a Jobs-page-specific backend overview endpoint that maps existing analysis jobs and analysis backtest jobs into one read model. Update the frontend Jobs hook, API client, and page row rendering to consume that unified read model while preserving the existing Jobs page layout.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, React, TypeScript, TanStack Query, Vite.

---

### Task 1: Backend Overview Endpoint

**Files:**
- Modify: `backend/schemas.py`
- Modify: `backend/routers/jobs.py`
- Test: `backend/tests/test_jobs_router.py`

- [ ] **Step 1: Write failing backend tests**

Add tests that create one analysis job and one analysis backtest job, then assert `GET /api/jobs/overview?status=pending&status=running&status=failed` returns both row kinds with the expected context.

- [ ] **Step 2: Run backend tests to verify failure**

Run: `pytest backend/tests/test_jobs_router.py -q`

Expected: failure because `/api/jobs/overview` does not exist.

- [ ] **Step 3: Add unified schema and endpoint**

Add `JobOverviewRead` to `backend/schemas.py` and implement `GET /api/jobs/overview` in `backend/routers/jobs.py`.

- [ ] **Step 4: Run backend tests to verify pass**

Run: `pytest backend/tests/test_jobs_router.py -q`

Expected: pass.

### Task 2: Frontend Unified Jobs Model

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/jobs.ts`
- Modify: `frontend/src/hooks/useJobs.ts`

- [ ] **Step 1: Add frontend types and API fetcher**

Add `JobKind`, `JobOverviewStatus`, and `JobOverview` types. Add `fetchJobOverview()` using `/jobs/overview`.

- [ ] **Step 2: Update Jobs hook**

Change `useJobs()` to use `fetchJobOverview()` and poll while any row is `pending` or `running`.

### Task 3: Jobs Page Rendering

**Files:**
- Modify: `frontend/src/pages/JobsPage.tsx`

- [ ] **Step 1: Preserve existing layout and row shape**

Update the page to render `JobOverview` rows while keeping the same grid structure, header, loading state, empty state, and status badge placement.

- [ ] **Step 2: Add backtest row labels and links**

Show `similarity >= N` for backtest rows, link completed backtests to `/backtest/runs/{backtest_run_id}`, and link source analysis rows to `/analyses/{analysis_id}` when no backtest run exists.

- [ ] **Step 3: Verify frontend build**

Run: `npm --prefix frontend run build`

Expected: TypeScript and Vite build pass.

### Task 4: Full Verification

**Files:**
- No code files unless verification exposes defects.

- [ ] **Step 1: Run focused backend and frontend checks**

Run:

```powershell
pytest backend/tests/test_jobs_router.py backend/tests/test_analysis_backtest_jobs_router.py -q
npm --prefix frontend run build
```

Expected: all checks pass.
