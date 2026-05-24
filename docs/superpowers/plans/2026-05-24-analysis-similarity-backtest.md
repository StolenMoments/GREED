# Analysis Similarity Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a background job that runs a KOSPI200-wide event-study backtest from one saved analysis by matching weighted rule-feature similarity.

**Architecture:** Add a focused analysis-similarity backtest engine under `scripts/backtest/`, persist its output into the existing backtest result tables, and track asynchronous execution in a new `analysis_backtest_jobs` table. Expose job APIs from the analyses router, then add an analysis detail panel that starts jobs, polls status, and links to `/backtest?runId=...`.

**Tech Stack:** Python 3.13, pandas, numpy, SQLAlchemy, FastAPI, Pydantic v2, React 19, TypeScript, Vite, @tanstack/react-query, Tailwind.

---

## File Structure

**Create**
- `scripts/backtest/analysis_similarity.py` - profile extraction, similarity scoring, KOSPI200 scan engine.
- `backend/tests/test_analysis_similarity_backtest.py` - engine unit tests.
- `backend/tests/test_analysis_backtest_jobs_router.py` - API/job tests.
- `frontend/src/api/analysisBacktests.ts` - analysis backtest job API client.
- `frontend/src/hooks/useAnalysisBacktests.ts` - query/mutation/polling hooks.
- `frontend/src/components/AnalysisBacktestPanel.tsx` - analysis detail panel.

**Modify**
- `backend/models.py` - add `AnalysisBacktestJob`; extend `BacktestRun`.
- `backend/database.py` - MariaDB migration for new table and new `backtest_runs` columns.
- `backend/schemas.py` - job request/read schemas; extend backtest run schemas.
- `backend/crud.py` - small CRUD helpers for analysis backtest jobs.
- `backend/routers/analyses.py` - add job create/list endpoints.
- `backend/routers/backtest.py` - keep read APIs compatible; expose new run metadata.
- `backend/routers/__init__.py` / `backend/main.py` only if a separate router is chosen. Preferred: no new router; use `analyses.py`.
- `scripts/backtest/persistence.py` - accept optional source metadata and alternate score buckets.
- `frontend/src/pages/AnalysisDetailPage.tsx` - render `AnalysisBacktestPanel`.
- `frontend/src/pages/BacktestPage.tsx` - honor `?runId=123` selection.
- `frontend/src/api/backtest.ts` - include new run metadata fields.
- `frontend/src/types/index.ts` - add analysis backtest job types if this project keeps shared API types there.

---

## Task 1: Data Model, Migration, and Schemas

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/database.py`
- Modify: `backend/schemas.py`
- Test: `backend/tests/test_analysis_backtest_jobs_router.py`

- [ ] **Step 1: Write failing model/schema/API smoke tests**

Create `backend/tests/test_analysis_backtest_jobs_router.py` with the shared in-memory app fixture pattern used by `backend/tests/test_backtest_router.py`.

```python
from __future__ import annotations

from collections.abc import Generator
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.models import Analysis, Run
from backend.routers.analyses import router as analyses_router


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    app = FastAPI()
    app.include_router(analyses_router)

    def override_get_db() -> Generator[Session, None, None]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(client: TestClient) -> Generator[Session, None, None]:
    override = client.app.dependency_overrides[get_db]
    session = next(override())
    try:
        yield session
    finally:
        session.close()


def _seed_analysis(db: Session) -> int:
    run = Run(memo="similarity backtest")
    db.add(run)
    db.flush()
    analysis = Analysis(
        run_id=run.id,
        ticker="005930",
        name="Samsung",
        name_initials="SS",
        model="rule",
        markdown="body",
        judgment="매수",
        trend="상승",
        cloud_position="구름 위",
        ma_alignment="정배열",
        created_at=datetime(2026, 5, 24, 9, 0, 0),
    )
    db.add(analysis)
    db.commit()
    return analysis.id


def test_create_analysis_backtest_job(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_id = _seed_analysis(db_session)
    scheduled: list[int] = []

    def fake_runner(job_id: int) -> None:
        scheduled.append(job_id)

    from backend.routers import analyses

    monkeypatch.setattr(analyses, "run_analysis_backtest_pipeline", fake_runner)

    response = client.post(
        f"/api/analyses/{analysis_id}/backtest-jobs",
        json={"similarity_threshold": 9},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["analysis_id"] == analysis_id
    assert body["status"] == "pending"
    assert body["similarity_threshold"] == 9
    assert body["backtest_run_id"] is None
    assert scheduled == [body["id"]]


def test_create_analysis_backtest_job_rejects_missing_analysis(client: TestClient) -> None:
    response = client.post(
        "/api/analyses/999999/backtest-jobs",
        json={"similarity_threshold": 9},
    )
    assert response.status_code == 404


def test_create_analysis_backtest_job_rejects_bad_threshold(client: TestClient, db_session: Session) -> None:
    analysis_id = _seed_analysis(db_session)
    response = client.post(
        f"/api/analyses/{analysis_id}/backtest-jobs",
        json={"similarity_threshold": 7},
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_analysis_backtest_jobs_router.py -q
```

Expected: FAIL because `AnalysisBacktestJob` schemas and endpoints do not exist.

- [ ] **Step 3: Add SQLAlchemy models**

In `backend/models.py`, add imports if needed:

```python
from sqlalchemy.orm import Mapped, mapped_column, relationship
```

Extend `BacktestRun`:

```python
    source_analysis_id: Mapped[int | None] = mapped_column(ForeignKey("analyses.id"), nullable=True)
    strategy_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    similarity_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

Add the new model:

```python
class AnalysisBacktestJob(Base):
    __tablename__ = "analysis_backtest_jobs"
    __table_args__ = (
        Index("ix_analysis_backtest_jobs_analysis_created", "analysis_id", "created_at"),
        Index("ix_analysis_backtest_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    similarity_threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    backtest_run_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_runs.id"), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=seoul_now,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Add MariaDB migration**

In `backend/database.py:_migrate_mariadb()`, after `backtest_runs` creation, add:

```python
        for col, typedef in [
            ("source_analysis_id", "INTEGER NULL"),
            ("strategy_kind", "VARCHAR(50) NULL"),
            ("similarity_threshold", "INTEGER NULL"),
        ]:
            conn.execute(text(f"ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS {col} {typedef}"))
```

Then after `backtest_stats` creation, add:

```python
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS analysis_backtest_jobs (
                    id INTEGER NOT NULL AUTO_INCREMENT,
                    analysis_id INTEGER NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    similarity_threshold INTEGER NOT NULL,
                    backtest_run_id INTEGER NULL,
                    error_message TEXT NULL,
                    created_at DATETIME NOT NULL,
                    completed_at DATETIME NULL,
                    PRIMARY KEY (id),
                    INDEX ix_analysis_backtest_jobs_analysis_created (analysis_id, created_at),
                    INDEX ix_analysis_backtest_jobs_status_created (status, created_at)
                )
                """
            )
        )
```

- [ ] **Step 5: Add Pydantic schemas**

In `backend/schemas.py`, add:

```python
class AnalysisBacktestJobCreate(BaseModel):
    similarity_threshold: Literal[8, 9, 10, 11] = 9


class AnalysisBacktestJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    analysis_id: int
    status: str
    similarity_threshold: int
    backtest_run_id: int | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None
```

Extend `BacktestRunSummary`:

```python
    source_analysis_id: int | None = None
    strategy_kind: str | None = None
    similarity_threshold: int | None = None
```

- [ ] **Step 6: Run targeted tests**

Run:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_analysis_backtest_jobs_router.py -q
```

Expected: still FAIL because CRUD/router endpoints are not implemented. That is correct for this task if model/schema import errors are gone.

- [ ] **Step 7: Commit**

```powershell
git add backend/models.py backend/database.py backend/schemas.py backend/tests/test_analysis_backtest_jobs_router.py
git commit -m "Add analysis backtest job schema"
```

---

## Task 2: Similarity Profile and Engine

**Files:**
- Create: `scripts/backtest/analysis_similarity.py`
- Modify: `scripts/backtest/persistence.py`
- Test: `backend/tests/test_analysis_similarity_backtest.py`

- [ ] **Step 1: Write failing engine tests**

Create `backend/tests/test_analysis_similarity_backtest.py`:

```python
from __future__ import annotations

from datetime import date

import pandas as pd

from scripts.backtest.analysis_similarity import (
    SimilarityProfile,
    analysis_score_bucket,
    bucket_macd_hist,
    bucket_rsi,
    bucket_volume,
    similarity_score,
)


def _profile(**overrides) -> SimilarityProfile:
    data = {
        "trend": "상승",
        "cloud_position": "구름 위",
        "ma_alignment": "정배열",
        "macd_hist_direction": "rising_positive",
        "rsi_bucket": "mid",
        "volume_bucket": "active",
        "strict_divergence": "none",
        "future_cloud_direction": "상승형",
    }
    data.update(overrides)
    return SimilarityProfile(**data)


def test_similarity_score_full_match_is_14() -> None:
    assert similarity_score(_profile(), _profile()) == 14


def test_similarity_score_does_not_reward_unknowns() -> None:
    base = _profile(rsi_bucket="unknown", volume_bucket="unknown")
    candidate = _profile(rsi_bucket="unknown", volume_bucket="unknown")
    assert similarity_score(base, candidate) == 12


def test_bucket_helpers() -> None:
    assert bucket_macd_hist(3.0, 2.0, 1.0) == "rising_positive"
    assert bucket_macd_hist(-3.0, -2.0, -1.0) == "falling_negative"
    assert bucket_macd_hist(None, -2.0, -1.0) == "unknown"
    assert bucket_rsi(35) == "low"
    assert bucket_rsi(55) == "mid"
    assert bucket_rsi(68) == "high"
    assert bucket_rsi(80) == "overheated"
    assert bucket_volume(0.6) == "dry"
    assert bucket_volume(0.9) == "normal"
    assert bucket_volume(1.1) == "active"


def test_analysis_score_bucket() -> None:
    assert analysis_score_bucket(8) == "8-9"
    assert analysis_score_bucket(10) == "10-11"
    assert analysis_score_bucket(12) == "12+"
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_analysis_similarity_backtest.py -q
```

Expected: FAIL because `scripts.backtest.analysis_similarity` does not exist.

- [ ] **Step 3: Implement profile helpers**

Create `scripts/backtest/analysis_similarity.py`:

```python
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from backtest.engine import HORIZONS, WARMUP_WEEKS, SignalRecord, StatRow, _f, _to_date, aggregate, build_combined
from rule_scorer.features import Features, extract_features_asof
from rule_scorer.score import score_features


SIMILARITY_THRESHOLDS = (8, 9, 10, 11)
SIMILARITY_WEIGHTS = {
    "cloud_position": 3,
    "ma_alignment": 3,
    "trend": 2,
    "macd_hist_direction": 2,
    "rsi_bucket": 1,
    "volume_bucket": 1,
    "strict_divergence": 1,
    "future_cloud_direction": 1,
}


@dataclass(frozen=True, slots=True)
class SimilarityProfile:
    trend: str
    cloud_position: str
    ma_alignment: str
    macd_hist_direction: str
    rsi_bucket: str
    volume_bucket: str
    strict_divergence: str
    future_cloud_direction: str


@dataclass(slots=True)
class AnalysisBacktestResult:
    records: list[SignalRecord] = field(default_factory=list)
    stats: list[StatRow] = field(default_factory=list)
    ticker_count: int = 0
    data_start: date | None = None
    data_end: date | None = None
    base_score: int = 0
    base_judgment: str = ""
    base_profile: SimilarityProfile | None = None


def bucket_macd_hist(current: float | None, prev: float | None, prev2: float | None) -> str:
    if current is None or prev is None or prev2 is None:
        return "unknown"
    if current > 0 and current > prev > prev2:
        return "rising_positive"
    if current < 0 and current < prev < prev2:
        return "falling_negative"
    return "other"


def bucket_rsi(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 45:
        return "low"
    if value <= 65:
        return "mid"
    if value <= 75:
        return "high"
    return "overheated"


def bucket_volume(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 0.7:
        return "dry"
    if value < 1.0:
        return "normal"
    return "active"


def _clean_divergence(value: str | None) -> str:
    return value if value in {"bullish", "bearish"} else "none"


def _clean_future_cloud(value: str | None) -> str:
    return value or "unknown"


def profile_from_features(features: Features) -> tuple[SimilarityProfile, int, str]:
    score = score_features(features)
    return (
        SimilarityProfile(
            trend=score.trend,
            cloud_position=score.cloud_position,
            ma_alignment=score.ma_alignment,
            macd_hist_direction=bucket_macd_hist(
                features.macd_hist,
                features.macd_hist_prev,
                features.macd_hist_prev2,
            ),
            rsi_bucket=bucket_rsi(features.rsi14),
            volume_bucket=bucket_volume(features.volume_ratio_20),
            strict_divergence=_clean_divergence(features.strict_divergence),
            future_cloud_direction=_clean_future_cloud(features.future_cloud_direction),
        ),
        score.total,
        score.judgment,
    )


def similarity_score(base: SimilarityProfile, candidate: SimilarityProfile) -> int:
    total = 0
    for field_name, weight in SIMILARITY_WEIGHTS.items():
        base_value = getattr(base, field_name)
        candidate_value = getattr(candidate, field_name)
        if base_value == "unknown" or candidate_value == "unknown":
            continue
        if base_value == candidate_value:
            total += weight
    return total


def analysis_score_bucket(score: int) -> str:
    if score >= 12:
        return "12+"
    if score >= 10:
        return "10-11"
    return "8-9"
```

- [ ] **Step 4: Run helper tests**

Run:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_analysis_similarity_backtest.py -q
```

Expected: PASS for helper tests.

- [ ] **Step 5: Add engine functions**

Append to `scripts/backtest/analysis_similarity.py`:

```python
def analysis_asof_index(combined: pd.DataFrame, analysis_created_at) -> int:
    price = combined[combined["close"].notna()].reset_index(drop=True)
    if price.empty:
        raise ValueError("CSV has no price rows")
    analysis_date = pd.to_datetime(analysis_created_at).date()
    dates = pd.to_datetime(price["date"]).dt.date
    candidates = [idx for idx, value in enumerate(dates) if value <= analysis_date]
    if not candidates:
        raise ValueError("No weekly row exists on or before analysis date")
    return candidates[-1]


def run_similarity_ticker(
    combined: pd.DataFrame,
    *,
    base_profile: SimilarityProfile,
    threshold: int,
    horizons: tuple[int, ...] = HORIZONS,
    warmup: int = WARMUP_WEEKS,
) -> list[SignalRecord]:
    if threshold not in SIMILARITY_THRESHOLDS:
        raise ValueError(f"Unsupported similarity threshold: {threshold}")

    price = combined[combined["close"].notna()].reset_index(drop=True)
    n = len(price)
    records: list[SignalRecord] = []
    last_entry_i = n - 2

    for i in range(warmup, last_entry_i + 1):
        features = extract_features_asof(combined, i)
        candidate_profile, _candidate_score, _candidate_judgment = profile_from_features(features)
        score = similarity_score(base_profile, candidate_profile)
        if score < threshold:
            continue

        entry_price = _f(price["open"].iloc[i + 1])
        if entry_price is None or entry_price <= 0:
            continue

        returns: dict[int, float | None] = {}
        for horizon in horizons:
            exit_i = i + horizon
            exit_close = _f(price["close"].iloc[exit_i]) if exit_i < n else None
            returns[horizon] = (exit_close / entry_price - 1) if exit_close is not None else None

        records.append(
            SignalRecord(
                ticker=features.ticker,
                name=features.name,
                signal_date=_to_date(price["date"].iloc[i]),
                score=score,
                score_bucket=analysis_score_bucket(score),
                entry_date=_to_date(price["date"].iloc[i + 1]),
                entry_price=entry_price,
                returns=returns,
            )
        )

    return records
```

- [ ] **Step 6: Add engine integration test**

Append to `backend/tests/test_analysis_similarity_backtest.py`:

```python
from scripts.backtest.analysis_similarity import run_similarity_ticker


def _combined_frame() -> pd.DataFrame:
    rows = []
    for i in range(140):
        close = 100.0 + i
        rows.append(
            {
                "date": str(pd.Timestamp("2020-01-06") + pd.Timedelta(days=7 * i))[:10],
                "ticker": "000001",
                "name": "Test",
                "open": close,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 1000,
                "trading_value": 100000,
                "ma20": close - 1,
                "ma60": close - 2,
                "ma120": close - 3,
                "atr14": 1,
                "atr14_pct": 0.01,
                "rsi14": 55,
                "macd_hist": 3,
                "volume_ratio_20": 1.2,
                "ichi_conv": close - 1,
                "ichi_base": close - 2,
                "cloud_top": close - 5,
                "cloud_bottom": close - 8,
                "strict_divergence": "",
                "ma20_60_cross": "",
                "ichi_lead1": close + 1,
                "ichi_lead2": close,
            }
        )
    df = pd.DataFrame(rows)
    df["macd_hist"] = [1, 2, *([3] * 138)]
    return df


def test_run_similarity_ticker_emits_records() -> None:
    base = _profile()
    records = run_similarity_ticker(_combined_frame(), base_profile=base, threshold=9, warmup=120)
    assert records
    assert records[0].score >= 9
    assert records[0].score_bucket in {"8-9", "10-11", "12+"}
    assert 4 in records[0].returns
```

- [ ] **Step 7: Run engine tests**

Run:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_analysis_similarity_backtest.py -q
```

Expected: PASS.

- [ ] **Step 8: Extend persistence metadata**

Modify `scripts/backtest/persistence.py:persist_run` signature:

```python
def persist_run(
    db: Session,
    *,
    buy_threshold: int,
    warmup_weeks: int,
    ticker_count: int,
    records: list[SignalRecord],
    stats: list[StatRow],
    data_start: date | None,
    data_end: date | None,
    notes: str | None = None,
    source_analysis_id: int | None = None,
    strategy_kind: str | None = None,
    similarity_threshold: int | None = None,
) -> int:
```

Set these fields on `BacktestRun`:

```python
        source_analysis_id=source_analysis_id,
        strategy_kind=strategy_kind,
        similarity_threshold=similarity_threshold,
```

- [ ] **Step 9: Commit**

```powershell
git add scripts/backtest/analysis_similarity.py scripts/backtest/persistence.py backend/tests/test_analysis_similarity_backtest.py
git commit -m "Add analysis similarity backtest engine"
```

---

## Task 3: CRUD Helpers and Background Pipeline

**Files:**
- Modify: `backend/crud.py`
- Modify: `backend/routers/analyses.py`
- Test: `backend/tests/test_analysis_backtest_jobs_router.py`

- [ ] **Step 1: Add CRUD helper tests**

Append to `backend/tests/test_analysis_backtest_jobs_router.py`:

```python
def test_list_analysis_backtest_jobs_latest_first(client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_id = _seed_analysis(db_session)

    from backend.routers import analyses
    monkeypatch.setattr(analyses, "run_analysis_backtest_pipeline", lambda job_id: None)

    first = client.post(f"/api/analyses/{analysis_id}/backtest-jobs", json={"similarity_threshold": 8}).json()
    second = client.post(f"/api/analyses/{analysis_id}/backtest-jobs", json={"similarity_threshold": 11}).json()

    response = client.get(f"/api/analyses/{analysis_id}/backtest-jobs")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [second["id"], first["id"]]
```

- [ ] **Step 2: Implement CRUD helpers**

In `backend/crud.py`, import:

```python
from backend.models import AnalysisBacktestJob
from backend.timezone import seoul_now
```

Add:

```python
def create_analysis_backtest_job(
    db: Session,
    *,
    analysis_id: int,
    similarity_threshold: int,
) -> AnalysisBacktestJob:
    job = AnalysisBacktestJob(
        analysis_id=analysis_id,
        similarity_threshold=similarity_threshold,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_analysis_backtest_job(db: Session, job_id: int) -> AnalysisBacktestJob | None:
    return db.get(AnalysisBacktestJob, job_id)


def get_analysis_backtest_jobs(db: Session, analysis_id: int) -> list[AnalysisBacktestJob]:
    stmt = (
        select(AnalysisBacktestJob)
        .where(AnalysisBacktestJob.analysis_id == analysis_id)
        .order_by(desc(AnalysisBacktestJob.created_at), desc(AnalysisBacktestJob.id))
    )
    return list(db.scalars(stmt).all())


def update_analysis_backtest_job_done(
    db: Session,
    job: AnalysisBacktestJob,
    backtest_run_id: int,
) -> None:
    job.status = "done"
    job.backtest_run_id = backtest_run_id
    job.error_message = None
    job.completed_at = seoul_now()
    db.commit()


def update_analysis_backtest_job_failed(
    db: Session,
    job: AnalysisBacktestJob,
    error_message: str,
) -> None:
    job.status = "failed"
    job.error_message = error_message
    job.completed_at = seoul_now()
    db.commit()
```

Ensure `select` and `desc` imports are present.

- [ ] **Step 3: Add endpoints with a temporary failure stub**

In `backend/routers/analyses.py`, add imports:

```python
from fastapi import BackgroundTasks
from backend.schemas import AnalysisBacktestJobCreate, AnalysisBacktestJobRead
from backend.crud import (
    create_analysis_backtest_job,
    get_analysis_backtest_job,
    get_analysis_backtest_jobs,
    update_analysis_backtest_job_failed,
)
from backend.database import SessionLocal
```

Add endpoints:

```python
@router.post(
    "/{analysis_id}/backtest-jobs",
    response_model=AnalysisBacktestJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_analysis_backtest_job_endpoint(
    analysis_id: int,
    payload: AnalysisBacktestJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> AnalysisBacktestJobRead:
    if get_analysis(db, analysis_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    job = create_analysis_backtest_job(
        db,
        analysis_id=analysis_id,
        similarity_threshold=payload.similarity_threshold,
    )
    background_tasks.add_task(run_analysis_backtest_pipeline, job.id)
    return job


@router.get("/{analysis_id}/backtest-jobs", response_model=list[AnalysisBacktestJobRead])
def list_analysis_backtest_jobs_endpoint(
    analysis_id: int,
    db: Session = Depends(get_db),
) -> list[AnalysisBacktestJobRead]:
    if get_analysis(db, analysis_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")
    return get_analysis_backtest_jobs(db, analysis_id)
```

Add a temporary failure stub so accidental unmocked execution does not silently succeed:

```python
def run_analysis_backtest_pipeline(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = get_analysis_backtest_job(db, job_id)
        if job is None:
            return
        update_analysis_backtest_job_failed(db, job, "pipeline not implemented")
    finally:
        db.close()
```

- [ ] **Step 4: Run router tests**

Run:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_analysis_backtest_jobs_router.py -q
```

Expected: PASS for create/list tests because tests monkeypatch the pipeline.

- [ ] **Step 5: Commit**

```powershell
git add backend/crud.py backend/routers/analyses.py backend/tests/test_analysis_backtest_jobs_router.py
git commit -m "Add analysis backtest job endpoints"
```

---

## Task 4: End-to-End Pipeline Persistence

**Files:**
- Modify: `backend/routers/analyses.py`
- Modify: `scripts/backtest/analysis_similarity.py`
- Test: `backend/tests/test_analysis_backtest_jobs_router.py`

- [ ] **Step 1: Add pipeline completion test with monkeypatched dependencies**

Append this test to `backend/tests/test_analysis_backtest_jobs_router.py`:

```python
def test_pipeline_marks_job_done_with_fake_runner(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_id = _seed_analysis(db_session)

    from backend import crud
    from backend.routers import analyses

    job = crud.create_analysis_backtest_job(
        db_session,
        analysis_id=analysis_id,
        similarity_threshold=9,
    )

    def fake_execute(*, db, analysis, similarity_threshold):
        return 123

    monkeypatch.setattr(analyses, "_execute_analysis_backtest", fake_execute)
    analyses.run_analysis_backtest_pipeline(job.id)

    saved = crud.get_analysis_backtest_job(db_session, job.id)
    assert saved is not None
    db_session.refresh(saved)
    assert saved.status == "done"
    assert saved.backtest_run_id == 123
```

- [ ] **Step 2: Implement pipeline wrapper**

In `backend/routers/analyses.py`, replace the temporary pipeline:

```python
def run_analysis_backtest_pipeline(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = get_analysis_backtest_job(db, job_id)
        if job is None or job.status != "pending":
            return
        analysis = get_analysis(db, job.analysis_id)
        if analysis is None:
            update_analysis_backtest_job_failed(db, job, "Analysis not found")
            return
        try:
            run_id = _execute_analysis_backtest(
                db=db,
                analysis=analysis,
                similarity_threshold=job.similarity_threshold,
            )
        except Exception as exc:
            update_analysis_backtest_job_failed(db, job, str(exc)[:1200])
            return
        update_analysis_backtest_job_done(db, job, run_id)
    finally:
        db.close()
```

Add `_execute_analysis_backtest`:

```python
def _execute_analysis_backtest(*, db: Session, analysis: Analysis, similarity_threshold: int) -> int:
    from scripts.backtest.analysis_similarity import run_analysis_similarity_backtest

    return run_analysis_similarity_backtest(
        db=db,
        analysis=analysis,
        similarity_threshold=similarity_threshold,
    )
```

Import `Analysis` from `backend.models` for typing.

- [ ] **Step 3: Implement KOSPI200 engine entrypoint**

Append to `scripts/backtest/analysis_similarity.py`:

```python
def run_analysis_similarity_backtest(
    *,
    db,
    analysis,
    similarity_threshold: int,
    universe_path: str | Path | None = None,
    warmup: int = WARMUP_WEEKS,
) -> int:
    from rule_scorer.score import BUY_THRESHOLD
    from backtest.data import load_weekly_ohlcv
    from backtest.persistence import persist_run
    from backtest.universe import DEFAULT_UNIVERSE_PATH, load_universe

    universe = load_universe(universe_path or DEFAULT_UNIVERSE_PATH)

    base_weekly = load_weekly_ohlcv(db, analysis.ticker)
    base_combined = build_combined(base_weekly, analysis.ticker, analysis.name)
    base_i = analysis_asof_index(base_combined, analysis.created_at)
    base_features = extract_features_asof(base_combined, base_i)
    base_profile, base_score, base_judgment = profile_from_features(base_features)

    all_records: list[SignalRecord] = []
    data_start: date | None = None
    data_end: date | None = None
    processed = 0

    for code, name in universe:
        weekly = load_weekly_ohlcv(db, code)
        if weekly.empty or len(weekly) <= warmup + 1:
            continue
        combined = build_combined(weekly, code, name)
        all_records.extend(
            run_similarity_ticker(
                combined,
                base_profile=base_profile,
                threshold=similarity_threshold,
                warmup=warmup,
            )
        )
        processed += 1
        first = weekly.index.min().date()
        last = weekly.index.max().date()
        data_start = first if data_start is None else min(data_start, first)
        data_end = last if data_end is None else max(data_end, last)

    stats = aggregate(all_records)
    notes = (
        f"analysis_similarity source_analysis_id={analysis.id}; "
        f"analysis_judgment={analysis.judgment}; "
        f"base_judgment={base_judgment}; base_score={base_score}; "
        f"similarity_threshold={similarity_threshold}; "
        f"base_profile={base_profile}"
    )
    return persist_run(
        db,
        buy_threshold=BUY_THRESHOLD,
        warmup_weeks=warmup,
        ticker_count=processed,
        records=all_records,
        stats=stats,
        data_start=data_start,
        data_end=data_end,
        notes=notes,
        source_analysis_id=analysis.id,
        strategy_kind="analysis_similarity",
        similarity_threshold=similarity_threshold,
    )
```

- [ ] **Step 4: Run tests**

Run:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_analysis_backtest_jobs_router.py backend/tests/test_analysis_similarity_backtest.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/routers/analyses.py scripts/backtest/analysis_similarity.py backend/tests/test_analysis_backtest_jobs_router.py
git commit -m "Run analysis similarity backtests as jobs"
```

---

## Task 5: Backtest Run Metadata and Query Parameter Selection

**Files:**
- Modify: `backend/routers/backtest.py`
- Modify: `backend/tests/test_backtest_router.py`
- Modify: `frontend/src/api/backtest.ts`
- Modify: `frontend/src/pages/BacktestPage.tsx`

- [ ] **Step 1: Add backend metadata test**

In `backend/tests/test_backtest_router.py`, update seeded `BacktestRun` in `_seed`:

```python
        source_analysis_id=42,
        strategy_kind="analysis_similarity",
        similarity_threshold=9,
```

Then assert in `test_run_detail_includes_stats`:

```python
    assert body["source_analysis_id"] == 42
    assert body["strategy_kind"] == "analysis_similarity"
    assert body["similarity_threshold"] == 9
```

- [ ] **Step 2: Run backend test**

Run:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_backtest_router.py -q
```

Expected: PASS if Task 1 schema extension is correct.

- [ ] **Step 3: Extend frontend API types**

In `frontend/src/api/backtest.ts`, add fields to `BacktestRunSummary`:

```typescript
  source_analysis_id: number | null;
  strategy_kind: string | null;
  similarity_threshold: number | null;
```

- [ ] **Step 4: Support `/backtest?runId=123`**

In `frontend/src/pages/BacktestPage.tsx`, import `useSearchParams`:

```typescript
import { useSearchParams } from 'react-router-dom';
```

Inside `BacktestPage`, read:

```typescript
const [searchParams] = useSearchParams();
const requestedRunId = Number(searchParams.get('runId'));
```

Update the existing default-selection effect:

```typescript
useEffect(() => {
  if (runs.length === 0 || runId !== null) return;
  const requested = Number.isInteger(requestedRunId)
    ? runs.find((run) => run.id === requestedRunId)
    : undefined;
  setRunId(requested?.id ?? runs[0].id);
}, [runs, runId, requestedRunId]);
```

In the run metadata section, display source metadata when present:

```tsx
{detail.strategy_kind === 'analysis_similarity' && (
  <span>
    {' '}· source analysis #{detail.source_analysis_id} · similarity {detail.similarity_threshold}
  </span>
)}
```

- [ ] **Step 5: Build frontend**

Run:

```powershell
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/tests/test_backtest_router.py frontend/src/api/backtest.ts frontend/src/pages/BacktestPage.tsx
git commit -m "Show analysis similarity backtest metadata"
```

---

## Task 6: Analysis Backtest API Client and Hooks

**Files:**
- Create: `frontend/src/api/analysisBacktests.ts`
- Create: `frontend/src/hooks/useAnalysisBacktests.ts`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add shared frontend types**

In `frontend/src/types/index.ts`, add:

```typescript
export type AnalysisBacktestJobStatus = 'pending' | 'done' | 'failed';

export interface AnalysisBacktestJob {
  id: number;
  analysis_id: number;
  status: AnalysisBacktestJobStatus;
  similarity_threshold: number;
  backtest_run_id: number | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface AnalysisBacktestJobCreate {
  similarity_threshold: 8 | 9 | 10 | 11;
}
```

- [ ] **Step 2: Create API client**

Create `frontend/src/api/analysisBacktests.ts`:

```typescript
import { apiClient } from './client';
import type { AnalysisBacktestJob, AnalysisBacktestJobCreate } from '../types';

export async function triggerAnalysisBacktest(
  analysisId: number,
  payload: AnalysisBacktestJobCreate,
): Promise<AnalysisBacktestJob> {
  const response = await apiClient.post<AnalysisBacktestJob>(
    `/analyses/${analysisId}/backtest-jobs`,
    payload,
  );
  return response.data;
}

export async function fetchAnalysisBacktestJobs(
  analysisId: number,
): Promise<AnalysisBacktestJob[]> {
  const response = await apiClient.get<AnalysisBacktestJob[]>(
    `/analyses/${analysisId}/backtest-jobs`,
  );
  return response.data;
}
```

- [ ] **Step 3: Create hooks**

Create `frontend/src/hooks/useAnalysisBacktests.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchAnalysisBacktestJobs,
  triggerAnalysisBacktest,
} from '../api/analysisBacktests';
import type { AnalysisBacktestJob, AnalysisBacktestJobCreate } from '../types';

export const analysisBacktestKeys = {
  all: ['analysis-backtests'] as const,
  list: (analysisId: number) =>
    [...analysisBacktestKeys.all, 'analysis', analysisId] as const,
};

export function useAnalysisBacktestJobs(analysisId: number | undefined) {
  return useQuery({
    queryKey: analysisBacktestKeys.list(analysisId ?? 0),
    queryFn: () => fetchAnalysisBacktestJobs(analysisId as number),
    enabled: analysisId !== undefined,
    refetchInterval: (query) => {
      const jobs = query.state.data;
      return jobs?.some((job) => job.status === 'pending') ? 2000 : false;
    },
  });
}

export function useTriggerAnalysisBacktest(analysisId: number | undefined) {
  const queryClient = useQueryClient();

  return useMutation<AnalysisBacktestJob, Error, AnalysisBacktestJobCreate>({
    mutationFn: (payload) => triggerAnalysisBacktest(analysisId as number, payload),
    onSuccess: () => {
      if (analysisId !== undefined) {
        void queryClient.invalidateQueries({
          queryKey: analysisBacktestKeys.list(analysisId),
        });
      }
      void queryClient.invalidateQueries({ queryKey: ['backtest'] });
    },
  });
}
```

- [ ] **Step 4: Build frontend**

Run:

```powershell
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/types/index.ts frontend/src/api/analysisBacktests.ts frontend/src/hooks/useAnalysisBacktests.ts
git commit -m "Add analysis backtest frontend hooks"
```

---

## Task 7: Analysis Detail UI Panel

**Files:**
- Create: `frontend/src/components/AnalysisBacktestPanel.tsx`
- Modify: `frontend/src/pages/AnalysisDetailPage.tsx`

- [ ] **Step 1: Create panel component**

Create `frontend/src/components/AnalysisBacktestPanel.tsx`:

```tsx
import { Link } from 'react-router-dom';
import { useState } from 'react';
import {
  useAnalysisBacktestJobs,
  useTriggerAnalysisBacktest,
} from '../hooks/useAnalysisBacktests';
import type { AnalysisBacktestJob } from '../types';

const THRESHOLDS = [8, 9, 10, 11] as const;

function statusLabel(job: AnalysisBacktestJob | undefined): string {
  if (!job) return 'No runs';
  if (job.status === 'pending') return 'Running';
  if (job.status === 'done') return 'Done';
  return 'Failed';
}

function statusTone(job: AnalysisBacktestJob | undefined): string {
  if (!job) return 'border-slate-800 text-slate-500';
  if (job.status === 'pending') return 'border-amber-300/30 text-amber-100';
  if (job.status === 'done') return 'border-emerald-300/30 text-emerald-100';
  return 'border-rose-300/30 text-rose-100';
}

export default function AnalysisBacktestPanel({ analysisId }: { analysisId: number }) {
  const [threshold, setThreshold] = useState<8 | 9 | 10 | 11>(9);
  const jobsQuery = useAnalysisBacktestJobs(analysisId);
  const trigger = useTriggerAnalysisBacktest(analysisId);
  const jobs = jobsQuery.data ?? [];
  const latest = jobs[0];
  const isRunning = latest?.status === 'pending' || trigger.isPending;

  async function handleRun() {
    await trigger.mutateAsync({ similarity_threshold: threshold });
  }

  return (
    <aside className="rounded-lg border border-amber-100/10 bg-slate-950/55 p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-slate-100">
            KOSPI200 유사도 백테스트
          </h3>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            이 분석의 룰 피처와 유사한 KOSPI200 과거 구간을 검증합니다.
          </p>
        </div>
        <span className={`rounded-full border px-3 py-1 text-xs font-semibold ${statusTone(latest)}`}>
          {statusLabel(latest)}
        </span>
      </div>

      <div className="mt-5">
        <p className="text-xs font-medium text-slate-500">유사도 임계값</p>
        <div className="mt-2 grid grid-cols-4 gap-2">
          {THRESHOLDS.map((value) => (
            <button
              className={[
                'h-9 rounded-md border text-sm font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70',
                threshold === value
                  ? 'border-amber-300 bg-amber-300 text-slate-950'
                  : 'border-slate-800 text-slate-300 hover:bg-slate-900',
              ].join(' ')}
              key={value}
              onClick={() => setThreshold(value)}
              type="button"
            >
              {value}
            </button>
          ))}
        </div>
      </div>

      <button
        className="mt-5 h-10 w-full rounded-md bg-amber-300 px-4 text-sm font-semibold text-slate-950 transition hover:bg-amber-200 disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/70"
        disabled={isRunning}
        onClick={() => void handleRun()}
        type="button"
      >
        {isRunning ? '실행 중' : '백테스트 실행'}
      </button>

      {latest?.status === 'failed' && latest.error_message ? (
        <p className="mt-3 rounded-md border border-rose-300/20 bg-rose-950/20 px-3 py-2 text-xs leading-5 text-rose-100">
          {latest.error_message}
        </p>
      ) : null}

      {latest?.status === 'done' && latest.backtest_run_id ? (
        <Link
          className="mt-4 block rounded-md border border-emerald-300/25 px-3 py-2 text-center text-sm font-semibold text-emerald-100 transition hover:bg-emerald-300/10"
          to={`/backtest?runId=${latest.backtest_run_id}`}
        >
          Backtest Run #{latest.backtest_run_id}
        </Link>
      ) : null}

      {jobs.length > 1 ? (
        <div className="mt-4 border-t border-amber-100/10 pt-3">
          <p className="text-xs font-medium text-slate-500">최근 실행</p>
          <div className="mt-2 space-y-1">
            {jobs.slice(1, 4).map((job) => (
              <div className="flex items-center justify-between gap-2 text-xs text-slate-500" key={job.id}>
                <span>#{job.id} · threshold {job.similarity_threshold}</span>
                {job.backtest_run_id ? (
                  <Link className="text-amber-100 hover:text-amber-200" to={`/backtest?runId=${job.backtest_run_id}`}>
                    run #{job.backtest_run_id}
                  </Link>
                ) : (
                  <span>{job.status}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </aside>
  );
}
```

- [ ] **Step 2: Render panel in analysis detail**

In `frontend/src/pages/AnalysisDetailPage.tsx`, import:

```typescript
import AnalysisBacktestPanel from '../components/AnalysisBacktestPanel';
```

Add it in the right column after `OutcomePanel`:

```tsx
        <AnalysisBacktestPanel analysisId={analysis.id} />
```

- [ ] **Step 3: Build frontend**

Run:

```powershell
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add frontend/src/components/AnalysisBacktestPanel.tsx frontend/src/pages/AnalysisDetailPage.tsx
git commit -m "Add analysis similarity backtest panel"
```

---

## Task 8: Integration Verification and Documentation

**Files:**
- Modify: `docs/기능정의.md`

- [ ] **Step 1: Run targeted backend tests**

Run:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_analysis_similarity_backtest.py backend/tests/test_analysis_backtest_jobs_router.py backend/tests/test_backtest_router.py -q
```

Expected: PASS.

- [ ] **Step 2: Run existing affected tests**

Run:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_main.py backend/tests/test_jobs_router.py -q
```

Expected: PASS. If `test_jobs_router.py` is slow, run the subset around job listing and analysis finalization first, then the full file before final completion.

- [ ] **Step 3: Build frontend**

Run:

```powershell
cd frontend
npm run build
```

Expected: PASS.

- [ ] **Step 4: Manual smoke test**

Start the backend and frontend using the existing project workflow. In the browser:

1. Open an analysis detail page.
2. Select threshold `9`.
3. Click `백테스트 실행`.
4. Confirm the panel shows `Running`.
5. Poll until `Backtest Run #...` appears.
6. Click the link and confirm `/backtest?runId=...` selects the generated run.

- [ ] **Step 5: Document the feature**

Add a short section to `docs/기능정의.md`:

```markdown
## Analysis Similarity Backtest

- 분석 상세에서 분석 1건을 기준으로 KOSPI200 전체 과거 주봉 유사 구간 백테스트를 실행할 수 있다.
- 유사도 임계값은 8, 9, 10, 11 중 선택한다.
- 결과는 기존 백테스트 결과 화면에서 조회하며, source analysis와 threshold가 저장된다.
```

- [ ] **Step 6: Commit docs**

```powershell
git add docs/기능정의.md
git commit -m "Document analysis similarity backtest"
```

---

## Self-Review Checklist

- Spec coverage:
  - Analysis-derived profile: Task 2 and Task 4.
  - Weighted similarity threshold 8/9/10/11: Task 2, Task 3, Task 7.
  - KOSPI200-wide background job: Task 3 and Task 4.
  - Existing backtest result reuse: Task 2, Task 4, Task 5.
  - Analysis detail UI and polling: Task 6 and Task 7.
  - `/backtest?runId=` deep link: Task 5.
- Compatibility:
  - Existing CLI `scripts.backtest.run` keeps working because new `persist_run` params default to `None`.
  - Existing `/api/backtest/runs` responses gain nullable fields only.
  - Existing `backtest_signals.score_bucket` remains readable; `strategy_kind` tells the UI how to interpret it.
- Verification:
  - Backend targeted tests pass.
  - Frontend build passes.
  - Manual smoke verifies a real job from analysis detail to backtest results.
