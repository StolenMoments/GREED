from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend import crud
from backend.database import Base, get_db
from backend.routers import jobs
from backend.routers.jobs import router, run_analysis_pipeline


VALID_MARKDOWN = """
## 판단
**매수**

## 기술적 지표 요약
- 추세: 상승
- 구름대 위치: 구름 위
- MA 배열: 정배열

## 매매 전략
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 진입 조건 | 20주선 지지 확인 | 75,000원 |
| 1차 목표 | 전고점 재도전 | 82,000 |
| 손절 기준 | 추세 이탈 | 71,500원 |

## 분석 근거
테스트 분석입니다.
"""


@pytest.fixture()
def test_db() -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    try:
        yield TestingSessionLocal
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(test_db: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(router)

    def override_get_db() -> Generator[Session, None, None]:
        session = test_db()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_trigger_analysis_creates_pending_job(
    client: TestClient,
    test_db: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called_job_ids: list[int] = []
    monkeypatch.setattr(jobs, "run_analysis_pipeline", lambda job_id: called_job_ids.append(job_id))
    with test_db() as db:
        run = crud.create_run(db, memo="job trigger")

    response = client.post("/api/jobs/trigger-analysis", json={"ticker": "5930", "run_id": run.id})

    assert response.status_code == 202
    body = response.json()
    assert body["ticker"] == "005930"
    assert body["run_id"] == run.id
    assert body["status"] == "pending"
    assert body["analysis_id"] is None
    assert called_job_ids == [body["id"]]


def test_trigger_analysis_returns_404_when_run_missing(client: TestClient) -> None:
    response = client.post("/api/jobs/trigger-analysis", json={"ticker": "005930", "run_id": 99999})

    assert response.status_code == 404
    assert response.json() == {"detail": "Run not found"}


def test_get_job_returns_job(client: TestClient, test_db: sessionmaker[Session]) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="get job")
        job = crud.create_job(db, ticker="005930", run_id=run.id)

    response = client.get(f"/api/jobs/{job.id}")

    assert response.status_code == 200
    assert response.json()["id"] == job.id


def test_list_jobs_returns_run_jobs_newest_first(client: TestClient, test_db: sessionmaker[Session]) -> None:
    with test_db() as db:
        first_run = crud.create_run(db, memo="first")
        second_run = crud.create_run(db, memo="second")
        older_job = crud.create_job(db, ticker="005930", run_id=first_run.id)
        newer_job = crud.create_job(db, ticker="000660", run_id=first_run.id)
        other_run_job = crud.create_job(db, ticker="035420", run_id=second_run.id)
        first_run_id = first_run.id
        older_job_id = older_job.id
        newer_job_id = newer_job.id
        other_run_job_id = other_run_job.id

    response = client.get(f"/api/jobs?run_id={first_run_id}")

    assert response.status_code == 200
    body = response.json()
    assert [job["id"] for job in body] == [newer_job_id, older_job_id]
    assert other_run_job_id not in [job["id"] for job in body]


def test_list_jobs_returns_404_when_run_missing(client: TestClient) -> None:
    response = client.get("/api/jobs?run_id=99999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Run not found"}


def test_get_job_returns_404_when_missing(client: TestClient) -> None:
    response = client.get("/api/jobs/99999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found"}


def test_run_analysis_pipeline_saves_analysis(
    test_db: sessionmaker[Session],
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="pipeline success")
        job = crud.create_job(db, ticker="005930", run_id=run.id)

    output_dir = tmp_path / "jobs" / str(job.id)
    output_dir.mkdir(parents=True)
    csv_path = output_dir / "005930_Samsung_weekly_20260421.csv"
    csv_path.write_text("ticker,name,close\n005930,Samsung,75000\n", encoding="utf-8-sig")

    monkeypatch.setattr(jobs, "SessionLocal", test_db)
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(jobs, "_resolve_stock_name", lambda ticker: "Samsung")
    monkeypatch.setattr(jobs, "_run_pick", lambda ticker, stock_name, output_dir: None)
    monkeypatch.setattr(jobs, "_run_claude", lambda csv_text: VALID_MARKDOWN)

    run_analysis_pipeline(job.id)

    with test_db() as db:
        saved_job = crud.get_job(db, job.id)
        assert saved_job is not None
        assert saved_job.status == "done"
        assert saved_job.analysis_id is not None

        analysis = crud.get_analysis(db, saved_job.analysis_id)
        assert analysis is not None
        assert analysis.ticker == "005930"
        assert analysis.name == "Samsung"
        assert analysis.model == "claude-code"
        assert analysis.judgment == "매수"
        assert analysis.entry_price == 75000.0


def test_run_analysis_pipeline_marks_pick_failure(
    test_db: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="pipeline failure")
        job = crud.create_job(db, ticker="005930", run_id=run.id)

    monkeypatch.setattr(jobs, "SessionLocal", test_db)
    monkeypatch.setattr(jobs, "_resolve_stock_name", lambda ticker: "Samsung")

    def fail_pick(ticker: str, stock_name: str, output_dir) -> None:
        raise ValueError("종목 데이터 없음: 005930")

    monkeypatch.setattr(jobs, "_run_pick", fail_pick)

    run_analysis_pipeline(job.id)

    with test_db() as db:
        saved_job = crud.get_job(db, job.id)
        assert saved_job is not None
        assert saved_job.status == "failed"
        assert saved_job.error_message == "pick: 종목 데이터 없음: 005930"


def test_run_analysis_pipeline_marks_claude_execution_failure(
    test_db: sessionmaker[Session],
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="claude failure")
        job = crud.create_job(db, ticker="005930", run_id=run.id)

    output_dir = tmp_path / "jobs" / str(job.id)
    output_dir.mkdir(parents=True)
    csv_path = output_dir / "005930_Samsung_weekly_20260421.csv"
    csv_path.write_text("ticker,name,close\n005930,Samsung,75000\n", encoding="utf-8-sig")

    monkeypatch.setattr(jobs, "SessionLocal", test_db)
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(jobs, "_resolve_stock_name", lambda ticker: "Samsung")
    monkeypatch.setattr(jobs, "_run_pick", lambda ticker, stock_name, output_dir: None)

    def fail_claude(csv_text: str) -> str:
        raise FileNotFoundError("claude")

    monkeypatch.setattr(jobs, "_run_claude", fail_claude)

    run_analysis_pipeline(job.id)

    with test_db() as db:
        saved_job = crud.get_job(db, job.id)
        assert saved_job is not None
        assert saved_job.status == "failed"
        assert saved_job.error_message == "claude: claude"


def test_run_claude_sends_prompt_via_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class Completed:
        returncode = 0
        stdout = "  analysis markdown  "
        stderr = ""

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return Completed()

    monkeypatch.setattr(jobs.subprocess, "run", fake_run)

    result = jobs._run_claude("ticker,name,close\n005930,Samsung,75000\n")

    assert result == "analysis markdown"
    assert captured["args"] == ["claude", "-p"]
    assert "005930" in str(captured["input"])
