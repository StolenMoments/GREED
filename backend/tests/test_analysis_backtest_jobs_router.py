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
from backend.models import Analysis, AnalysisBacktestJob, BacktestRun, PriceBar, Run
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
    app.state.TestingSessionLocal = TestingSessionLocal

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
        judgment="buy",
        trend="up",
        cloud_position="above",
        ma_alignment="bullish",
        created_at=datetime(2026, 5, 24, 9, 0, 0),
    )
    db.add(analysis)
    db.commit()
    return analysis.id


def test_create_analysis_backtest_job(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_id = _seed_analysis(db_session)
    scheduled: list[int] = []

    def fake_runner(job_id: int) -> None:
        scheduled.append(job_id)

    from backend.routers import analyses

    monkeypatch.setattr(analyses, "run_analysis_backtest_pipeline", fake_runner)

    response = client.post(
        f"/api/analyses/{analysis_id}/backtest-jobs",
        json={},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["analysis_id"] == analysis_id
    assert body["status"] == "pending"
    assert body["similarity_threshold"] == 12
    assert body["backtest_run_id"] is None
    assert scheduled == [body["id"]]


def test_create_analysis_backtest_job_rejects_missing_analysis(client: TestClient) -> None:
    response = client.post(
        "/api/analyses/999999/backtest-jobs",
        json={},
    )

    assert response.status_code == 404


def test_create_analysis_backtest_job_rejects_invalid_threshold(
    client: TestClient,
    db_session: Session,
) -> None:
    analysis_id = _seed_analysis(db_session)

    response = client.post(
        f"/api/analyses/{analysis_id}/backtest-jobs",
        json={"similarity_threshold": 9},
    )

    assert response.status_code == 422


def test_list_analysis_backtest_jobs(client: TestClient, db_session: Session) -> None:
    analysis_id = _seed_analysis(db_session)

    response = client.get(f"/api/analyses/{analysis_id}/backtest-jobs")

    assert response.status_code == 200
    assert response.json() == []


def test_analysis_backtest_pipeline_persists_run_metadata(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_id = _seed_analysis(db_session)
    job = AnalysisBacktestJob(
        analysis_id=analysis_id,
        status="pending",
        similarity_threshold=12,
    )
    db_session.add(job)
    db_session.commit()
    job_id = job.id

    from backend.routers import analyses
    from scripts.backtest.analysis_similarity import AnalysisBacktestResult
    import scripts.backtest.analysis_similarity as analysis_similarity

    def fake_backtest(db: Session, analysis: Analysis, *, threshold: int) -> AnalysisBacktestResult:
        assert analysis.id == analysis_id
        assert threshold == 12
        return AnalysisBacktestResult(
            ticker_count=3,
            data_start=None,
            data_end=None,
            base_score=6,
            base_judgment="buy",
        )

    monkeypatch.setattr(analyses, "SessionLocal", client.app.state.TestingSessionLocal)
    monkeypatch.setattr(analysis_similarity, "run_analysis_contract_backtest", fake_backtest)

    analyses.run_analysis_backtest_pipeline(job_id)

    db_session.expire_all()
    saved_job = db_session.get(AnalysisBacktestJob, job_id)
    assert saved_job is not None
    assert saved_job.status == "done"
    assert saved_job.completed_at is not None
    assert saved_job.backtest_run_id is not None

    run = db_session.get(BacktestRun, saved_job.backtest_run_id)
    assert run is not None
    assert run.source_analysis_id == analysis_id
    assert run.strategy_kind == "analysis_contract"
    assert run.similarity_threshold == 12
    assert run.buy_threshold == 12
    assert run.ticker_count == 3


def test_analysis_backtest_pipeline_marks_failure(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_id = _seed_analysis(db_session)
    job = AnalysisBacktestJob(
        analysis_id=analysis_id,
        status="pending",
        similarity_threshold=10,
    )
    db_session.add(job)
    db_session.commit()
    job_id = job.id

    from backend.routers import analyses
    import scripts.backtest.analysis_similarity as analysis_similarity

    def fake_backtest(db: Session, analysis: Analysis, *, threshold: int):
        raise RuntimeError("not enough data")

    monkeypatch.setattr(analyses, "SessionLocal", client.app.state.TestingSessionLocal)
    monkeypatch.setattr(analysis_similarity, "run_analysis_contract_backtest", fake_backtest)

    analyses.run_analysis_backtest_pipeline(job_id)

    db_session.expire_all()
    saved_job = db_session.get(AnalysisBacktestJob, job_id)
    assert saved_job is not None
    assert saved_job.status == "failed"
    assert saved_job.completed_at is not None
    assert saved_job.error_message == "not enough data"


def test_analysis_backtest_pipeline_rolls_back_before_marking_failure(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_id = _seed_analysis(db_session)
    job = AnalysisBacktestJob(
        analysis_id=analysis_id,
        status="pending",
        similarity_threshold=10,
    )
    db_session.add(job)
    db_session.commit()
    job_id = job.id

    from backend.routers import analyses
    import scripts.backtest.analysis_similarity as analysis_similarity

    def fake_backtest(db: Session, analysis: Analysis, *, threshold: int):
        duplicate = {
            "ticker": "009150",
            "interval": "1w",
            "bar_date": datetime(2026, 5, 18).date(),
            "open": 1,
            "high": 2,
            "low": 1,
            "close": 2,
            "volume": 10,
            "trading_value": 20,
            "fetched_at": datetime(2026, 5, 24, 9, 0, 0),
        }
        db.add(PriceBar(**duplicate))
        db.add(PriceBar(**duplicate))
        db.flush()

    monkeypatch.setattr(analyses, "SessionLocal", client.app.state.TestingSessionLocal)
    monkeypatch.setattr(analysis_similarity, "run_analysis_contract_backtest", fake_backtest)

    analyses.run_analysis_backtest_pipeline(job_id)

    db_session.expire_all()
    saved_job = db_session.get(AnalysisBacktestJob, job_id)
    assert saved_job is not None
    assert saved_job.status == "failed"
    assert saved_job.completed_at is not None
    assert "UNIQUE constraint failed" in saved_job.error_message


def test_delete_analysis_cleans_backtest_references(client: TestClient, db_session: Session) -> None:
    analysis_id = _seed_analysis(db_session)
    run = BacktestRun(
        universe="KOSPI200",
        buy_threshold=10,
        horizons="4,8,12,26",
        warmup_weeks=120,
        data_start=None,
        data_end=None,
        ticker_count=1,
        signal_count=0,
        notes=None,
        source_analysis_id=analysis_id,
        strategy_kind="analysis_similarity",
        similarity_threshold=10,
    )
    job = AnalysisBacktestJob(
        analysis_id=analysis_id,
        status="done",
        similarity_threshold=10,
    )
    db_session.add_all([run, job])
    db_session.commit()
    run_id = run.id
    job_id = job.id

    response = client.delete(f"/api/analyses/{analysis_id}")

    assert response.status_code == 204
    db_session.expire_all()
    saved_run = db_session.get(BacktestRun, run_id)
    assert saved_run is not None
    assert saved_run.source_analysis_id is None
    assert saved_run.strategy_kind == "analysis_similarity"
    assert db_session.get(AnalysisBacktestJob, job_id) is None
