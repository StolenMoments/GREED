from __future__ import annotations

import json
import os
from collections.abc import Generator
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend import crud
from backend.database import Base, get_db
from backend.models import KrxStock
from backend.routers import jobs
from backend.routers.jobs import router, run_analysis_pipeline
from backend.timezone import seoul_now


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


INVALID_PRICE_MARKDOWN = """
## 종목 분석 결과

### 1. 현재 구조 요약
- 추세: 상승
- 구름대 위치: 구름 위
- MA 배열: 혼조

### 4. 매매 판정
**홀드**

### 5. 진입/청산 시나리오
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 눌림 진입 | 1차 지지선 부근 조정 확인 | 1,980원 |
| 돌파 진입 | 1차 저항 주봉 종가 돌파 확인 | 1,998원 |
| 1차 목표 | 2차 저항 도달 | 1,963원 |
| 손절 기준 | 2차 지지 이탈 | 1,626원 |
"""


MIXED_ENTRY_MARKDOWN = """
## 종목 분석 결과

### 1. 현재 구조 요약
- 추세: 상승
- 구름대 위치: 구름 위
- MA 배열: 정배열

### 4. 매매 판정
**매수**

### 5. 진입/청산 시나리오
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 눌림 진입 | 전환선 부근 조정 시 기준선 지지 확인 | 9,600~9,775원 |
| 돌파 진입 | 직전 고가 종가 기준 돌파 확인 | 12,000원 이상 |
| 1차 목표 | 직전 주 고가 저항 도달 | 11,920원 |
| 손절 기준 | 기준선 종가 하향 이탈 | 9,600원 아래 종가 |
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


class FakeProcess:
    pid = 1234


def _write_csv(output_dir: Path, filename: str, close: str = "75000") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / filename
    csv_path.write_text(f"ticker,name,close\n005930,Samsung,{close}\n", encoding="utf-8-sig")
    return csv_path


def test_system_prompt_uses_conservative_buy_gate() -> None:
    assert "매수 신뢰성 필터" in jobs.KR_SYSTEM_PROMPT
    assert "기본 구조 조건은 구름 위 + MA 정배열" in jobs.KR_SYSTEM_PROMPT
    assert "MACD hist 양전환 또는 증가만으로는 매수 판정 금지" in jobs.KR_SYSTEM_PROMPT
    assert "확인 신호가 2개 이상" in jobs.KR_SYSTEM_PROMPT
    assert "지지권 근처 선제 진입 또는 저항 돌파 예상 진입도" in jobs.KR_SYSTEM_PROMPT
    assert "조건이 아직 충족되지 않은 경우 최종 판정은 매수가 아니라 홀드" not in jobs.KR_SYSTEM_PROMPT
    assert "구름 위 + MA 정배열이라도 확인 신호 2개 미만이면 홀드" in jobs.KR_SYSTEM_PROMPT
    assert "다음 리스크가 2개 이상이면 매수 판정을 금지" in jobs.KR_SYSTEM_PROMPT
    assert "atr14_pct >= 6%" in jobs.KR_SYSTEM_PROMPT
    assert "구름 위 + MA 정배열 + RSI < 70 → 매수를 우선 판정" not in jobs.KR_SYSTEM_PROMPT


def test_us_system_prompt_keeps_conservative_buy_gate() -> None:
    assert "미국 주식시장 전문 기술적 분석가" in jobs.US_SYSTEM_PROMPT
    assert "매수 신뢰성 필터" in jobs.US_SYSTEM_PROMPT
    assert "기본 구조 조건은 구름 위 + MA 정배열" in jobs.US_SYSTEM_PROMPT
    assert "MACD hist 양전환 또는 증가만으로는 매수 판정 금지" in jobs.US_SYSTEM_PROMPT
    assert "확인 신호가 2개 이상" in jobs.US_SYSTEM_PROMPT
    assert "구름 위 + MA 정배열이라도 확인 신호 2개 미만이면 홀드" in jobs.US_SYSTEM_PROMPT
    assert "가격은 가능하면 실제 숫자와 달러 단위로 쓰고" in jobs.US_SYSTEM_PROMPT


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


def test_trigger_analysis_keeps_us_ticker(
    client: TestClient,
    test_db: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called_job_ids: list[int] = []
    monkeypatch.setattr(jobs, "run_analysis_pipeline", lambda job_id: called_job_ids.append(job_id))
    with test_db() as db:
        run = crud.create_run(db, memo="us job trigger")

    response = client.post("/api/jobs/trigger-analysis", json={"ticker": "aapl", "run_id": run.id})

    assert response.status_code == 202
    body = response.json()
    assert body["ticker"] == "AAPL"
    assert called_job_ids == [body["id"]]


def test_trigger_analysis_resolves_exact_krx_name(
    client: TestClient,
    test_db: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called_job_ids: list[int] = []
    monkeypatch.setattr(jobs, "run_analysis_pipeline", lambda job_id: called_job_ids.append(job_id))
    with test_db() as db:
        run = crud.create_run(db, memo="krx name trigger")
        db.add(KrxStock(code="003550", name="LG", name_initials="", updated_at=seoul_now()))
        db.commit()

    response = client.post("/api/jobs/trigger-analysis", json={"ticker": "LG", "run_id": run.id})

    assert response.status_code == 202
    body = response.json()
    assert body["ticker"] == "003550"
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


def test_list_jobs_filters_by_status(client: TestClient, test_db: sessionmaker[Session]) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="status filter")
        pending_job = crud.create_job(db, ticker="005930", run_id=run.id)
        failed_job = crud.create_job(db, ticker="000660", run_id=run.id)
        done_job = crud.create_job(db, ticker="035420", run_id=run.id)
        failed_job.status = "failed"
        done_job.status = "done"
        db.commit()
        pending_job_id = pending_job.id
        failed_job_id = failed_job.id
        done_job_id = done_job.id

    response = client.get("/api/jobs?status=pending&status=failed")

    assert response.status_code == 200
    job_ids = [job["id"] for job in response.json()]
    assert job_ids == [failed_job_id, pending_job_id]
    assert done_job_id not in job_ids


def test_list_jobs_filters_by_run_and_status(client: TestClient, test_db: sessionmaker[Session]) -> None:
    with test_db() as db:
        first_run = crud.create_run(db, memo="first")
        second_run = crud.create_run(db, memo="second")
        first_failed_job = crud.create_job(db, ticker="005930", run_id=first_run.id)
        first_done_job = crud.create_job(db, ticker="000660", run_id=first_run.id)
        second_failed_job = crud.create_job(db, ticker="035420", run_id=second_run.id)
        first_failed_job.status = "failed"
        first_done_job.status = "done"
        second_failed_job.status = "failed"
        db.commit()
        first_run_id = first_run.id
        first_failed_job_id = first_failed_job.id
        first_done_job_id = first_done_job.id
        second_failed_job_id = second_failed_job.id

    response = client.get(f"/api/jobs?run_id={first_run_id}&status=failed")

    assert response.status_code == 200
    job_ids = [job["id"] for job in response.json()]
    assert job_ids == [first_failed_job_id]
    assert first_done_job_id not in job_ids
    assert second_failed_job_id not in job_ids


def test_list_jobs_rejects_invalid_status(client: TestClient) -> None:
    response = client.get("/api/jobs?status=running")

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid job status: running"}


def test_list_jobs_returns_404_when_run_missing(client: TestClient) -> None:
    response = client.get("/api/jobs?run_id=99999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Run not found"}


def test_get_job_returns_404_when_missing(client: TestClient) -> None:
    response = client.get("/api/jobs/99999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found"}


def test_run_analysis_pipeline_starts_model_process_and_keeps_job_pending(
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="pipeline start")
        job = crud.create_job(db, ticker="005930", run_id=run.id)

    output_dir = tmp_path / "jobs" / str(job.id)
    captured: dict[str, object] = {}

    def fake_pick(ticker: str, stock_name: str, output_dir: Path) -> None:
        _write_csv(output_dir, "KOSPI_005930_Samsung_weekly_20260507.csv")

    def fake_runner(
        csv_text: str,
        system_prompt: str,
        analysis_path: Path,
        prompt_path: Path,
        stdout_path: Path,
        stderr_path: Path,
        pid_path: Path,
        exit_code_path: Path,
    ) -> FakeProcess:
        captured.update(
            {
                "csv_text": csv_text,
                "system_prompt": system_prompt,
                "analysis_path": analysis_path,
                "prompt_path": prompt_path,
                "stdout_path": stdout_path,
                "stderr_path": stderr_path,
                "pid_path": pid_path,
                "exit_code_path": exit_code_path,
            }
        )
        return FakeProcess()

    monkeypatch.setattr(jobs, "SessionLocal", test_db)
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(jobs, "_resolve_stock_name", lambda db, ticker: "Samsung")
    monkeypatch.setattr(jobs, "_run_pick", fake_pick)
    monkeypatch.setattr(jobs, "_run_claude", fake_runner)

    run_analysis_pipeline(job.id)

    with test_db() as db:
        saved_job = crud.get_job(db, job.id)
        assert saved_job is not None
        assert saved_job.status == "pending"
        assert saved_job.analysis_id is None

    assert "005930" in str(captured["csv_text"])
    assert captured["analysis_path"] == output_dir / jobs.ANALYSIS_FILENAME
    assert captured["prompt_path"] == output_dir / jobs.PROMPT_FILENAME
    assert captured["stdout_path"] == output_dir / jobs.STDOUT_LOG_FILENAME
    assert captured["stderr_path"] == output_dir / jobs.STDERR_LOG_FILENAME
    assert captured["pid_path"] == output_dir / jobs.PID_FILENAME
    assert captured["exit_code_path"] == output_dir / jobs.EXIT_CODE_FILENAME


def test_run_analysis_pipeline_reuses_today_root_csv(
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="pipeline reuse")
        job = crud.create_job(db, ticker="005930", run_id=run.id)

    today = jobs.seoul_now().strftime("%Y%m%d")
    root_csv = _write_csv(tmp_path, f"KOSPI_005930_Samsung_weekly_{today}.csv", close="76000")
    output_dir = tmp_path / "jobs" / str(job.id)
    captured: dict[str, object] = {}
    pick_calls: list[tuple[str, str, Path]] = []

    def fake_runner(
        csv_text: str,
        system_prompt: str,
        analysis_path: Path,
        prompt_path: Path,
        stdout_path: Path,
        stderr_path: Path,
        pid_path: Path,
        exit_code_path: Path,
    ) -> FakeProcess:
        captured["csv_text"] = csv_text
        captured["analysis_path"] = analysis_path
        return FakeProcess()

    monkeypatch.setattr(jobs, "SessionLocal", test_db)
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(jobs, "_resolve_stock_name", lambda db, ticker: "Samsung")
    monkeypatch.setattr(jobs, "_run_pick", lambda *args: pick_calls.append(args))
    monkeypatch.setattr(jobs, "_run_claude", fake_runner)

    run_analysis_pipeline(job.id)

    copied_csv = output_dir / root_csv.name
    cached_csv = tmp_path / jobs.CHART_CACHE_DIR_NAME / today / root_csv.name
    assert pick_calls == []
    assert cached_csv.exists()
    assert copied_csv.exists()
    assert "76000" in str(captured["csv_text"])
    assert captured["analysis_path"] == output_dir / jobs.ANALYSIS_FILENAME


def test_run_analysis_pipeline_reuses_today_chart_cache_csv(
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="pipeline cache reuse")
        job = crud.create_job(db, ticker="005930", run_id=run.id)

    today = jobs.seoul_now().strftime("%Y%m%d")
    cache_dir = tmp_path / jobs.CHART_CACHE_DIR_NAME / today
    cache_csv = _write_csv(cache_dir, f"KOSPI_005930_Samsung_weekly_{today}.csv", close="78000")
    output_dir = tmp_path / "jobs" / str(job.id)
    captured: dict[str, object] = {}
    pick_calls: list[tuple[str, str, Path]] = []

    def fake_runner(csv_text: str, *args: object) -> FakeProcess:
        captured["csv_text"] = csv_text
        return FakeProcess()

    monkeypatch.setattr(jobs, "SessionLocal", test_db)
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(jobs, "_resolve_stock_name", lambda db, ticker: "Samsung")
    monkeypatch.setattr(jobs, "_run_pick", lambda *args: pick_calls.append(args))
    monkeypatch.setattr(jobs, "_run_claude", fake_runner)

    run_analysis_pipeline(job.id)

    assert pick_calls == []
    assert (output_dir / cache_csv.name).exists()
    assert "78000" in str(captured["csv_text"])


def test_run_analysis_pipeline_uses_db_stock_name_when_resolver_fails(
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        db.add(KrxStock(code="129920", name="대성하이텍", name_initials="ㄷㅅㅎㅇㅌ", updated_at=seoul_now()))
        db.commit()
        run = crud.create_run(db, memo="pipeline db stock name")
        job = crud.create_job(db, ticker="129920", run_id=run.id)

    today = jobs.seoul_now().strftime("%Y%m%d")
    output_dir = tmp_path / "jobs" / str(job.id)
    pick_calls: list[tuple[str, str, Path]] = []

    def fake_pick(ticker: str, stock_name: str, output_dir: Path) -> None:
        pick_calls.append((ticker, stock_name, output_dir))
        csv_path = output_dir / f"129920_{stock_name}_weekly_{today}.csv"
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path.write_text(f"ticker,name,close\n129920,{stock_name},10540\n", encoding="utf-8-sig")

    monkeypatch.setattr(jobs, "SessionLocal", test_db)
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(jobs, "_run_pick", fake_pick)
    monkeypatch.setattr(jobs, "_run_claude", lambda *args: FakeProcess())

    run_analysis_pipeline(job.id)

    cache_dir = tmp_path / jobs.CHART_CACHE_DIR_NAME / today
    assert pick_calls == [("129920", "대성하이텍", cache_dir)]
    assert (output_dir / f"129920_대성하이텍_weekly_{today}.csv").exists()


def test_run_analysis_pipeline_ignores_nameless_cache_when_db_name_exists(
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        db.add(KrxStock(code="129920", name="대성하이텍", name_initials="ㄷㅅㅎㅇㅌ", updated_at=seoul_now()))
        db.commit()
        run = crud.create_run(db, memo="pipeline nameless cache")
        job = crud.create_job(db, ticker="129920", run_id=run.id)

    today = jobs.seoul_now().strftime("%Y%m%d")
    cache_dir = tmp_path / jobs.CHART_CACHE_DIR_NAME / today
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"129920_weekly_{today}.csv").write_text(
        "ticker,name,close\n129920,,10000\n",
        encoding="utf-8-sig",
    )
    output_dir = tmp_path / "jobs" / str(job.id)
    pick_calls: list[tuple[str, str, Path]] = []
    runner_csv_texts: list[str] = []

    def fake_pick(ticker: str, stock_name: str, output_dir: Path) -> None:
        pick_calls.append((ticker, stock_name, output_dir))
        csv_path = output_dir / f"129920_{stock_name}_weekly_{today}.csv"
        csv_path.write_text(f"ticker,name,close\n129920,{stock_name},10540\n", encoding="utf-8-sig")

    def fake_runner(csv_text: str, *args: object) -> FakeProcess:
        runner_csv_texts.append(csv_text)
        return FakeProcess()

    monkeypatch.setattr(jobs, "SessionLocal", test_db)
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(jobs, "_run_pick", fake_pick)
    monkeypatch.setattr(jobs, "_run_claude", fake_runner)

    run_analysis_pipeline(job.id)

    assert pick_calls == [("129920", "대성하이텍", cache_dir)]
    assert (output_dir / f"129920_대성하이텍_weekly_{today}.csv").exists()
    assert "대성하이텍" in runner_csv_texts[0]
    assert "10000" not in runner_csv_texts[0]


def test_run_analysis_pipeline_runs_pick_when_today_root_csv_is_missing(
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="pipeline no reuse")
        job = crud.create_job(db, ticker="005930", run_id=run.id)

    _write_csv(tmp_path, "005930_Samsung_weekly_20260421.csv", close="74000")
    output_dir = tmp_path / "jobs" / str(job.id)
    pick_calls: list[tuple[str, str, Path]] = []
    captured: dict[str, object] = {}

    def fake_pick(ticker: str, stock_name: str, output_dir: Path) -> None:
        pick_calls.append((ticker, stock_name, output_dir))
        _write_csv(output_dir, "KOSPI_005930_Samsung_weekly_20260507.csv", close="77000")

    def fake_runner(csv_text: str, *args: object) -> FakeProcess:
        captured["csv_text"] = csv_text
        return FakeProcess()

    monkeypatch.setattr(jobs, "SessionLocal", test_db)
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(jobs, "_resolve_stock_name", lambda db, ticker: "Samsung")
    monkeypatch.setattr(jobs, "_run_pick", fake_pick)
    monkeypatch.setattr(jobs, "_run_claude", fake_runner)

    run_analysis_pipeline(job.id)

    cache_dir = tmp_path / jobs.CHART_CACHE_DIR_NAME / jobs.seoul_now().strftime("%Y%m%d")
    assert pick_calls == [("005930", "Samsung", cache_dir)]
    assert (output_dir / "KOSPI_005930_Samsung_weekly_20260507.csv").exists()
    assert "77000" in str(captured["csv_text"])


def test_run_analysis_pipeline_reuses_csv_created_by_previous_job(
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="pipeline shared cache")
        first_job = crud.create_job(db, ticker="005930", run_id=run.id)
        second_job = crud.create_job(db, ticker="005930", run_id=run.id)
        first_job_id = first_job.id
        second_job_id = second_job.id

    today = jobs.seoul_now().strftime("%Y%m%d")
    pick_calls: list[tuple[str, str, Path]] = []
    runner_csv_texts: list[str] = []

    def fake_pick(ticker: str, stock_name: str, output_dir: Path) -> None:
        pick_calls.append((ticker, stock_name, output_dir))
        _write_csv(output_dir, f"KOSPI_005930_Samsung_weekly_{today}.csv", close="79000")

    def fake_runner(csv_text: str, *args: object) -> FakeProcess:
        runner_csv_texts.append(csv_text)
        return FakeProcess()

    monkeypatch.setattr(jobs, "SessionLocal", test_db)
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(jobs, "_resolve_stock_name", lambda db, ticker: "Samsung")
    monkeypatch.setattr(jobs, "_run_pick", fake_pick)
    monkeypatch.setattr(jobs, "_run_claude", fake_runner)

    run_analysis_pipeline(first_job_id)
    run_analysis_pipeline(second_job_id)

    cache_dir = tmp_path / jobs.CHART_CACHE_DIR_NAME / today
    assert pick_calls == [("005930", "Samsung", cache_dir)]
    assert (tmp_path / "jobs" / str(first_job_id) / f"KOSPI_005930_Samsung_weekly_{today}.csv").exists()
    assert (tmp_path / "jobs" / str(second_job_id) / f"KOSPI_005930_Samsung_weekly_{today}.csv").exists()
    assert all("79000" in csv_text for csv_text in runner_csv_texts)


def test_run_analysis_pipeline_ignores_yesterday_root_csv(
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="pipeline yesterday")
        job = crud.create_job(db, ticker="005930", run_id=run.id)

    yesterday = (jobs.seoul_now() - timedelta(days=1)).strftime("%Y%m%d")
    _write_csv(tmp_path, f"005930_Samsung_weekly_{yesterday}.csv", close="74000")
    output_dir = tmp_path / "jobs" / str(job.id)
    pick_calls: list[tuple[str, str, Path]] = []

    def fake_pick(ticker: str, stock_name: str, output_dir: Path) -> None:
        pick_calls.append((ticker, stock_name, output_dir))
        _write_csv(output_dir, "KOSPI_005930_Samsung_weekly_20260507.csv", close="77000")

    monkeypatch.setattr(jobs, "SessionLocal", test_db)
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(jobs, "_resolve_stock_name", lambda db, ticker: "Samsung")
    monkeypatch.setattr(jobs, "_run_pick", fake_pick)
    monkeypatch.setattr(jobs, "_run_claude", lambda *args: FakeProcess())

    run_analysis_pipeline(job.id)

    cache_dir = tmp_path / jobs.CHART_CACHE_DIR_NAME / jobs.seoul_now().strftime("%Y%m%d")
    assert pick_calls == [("005930", "Samsung", cache_dir)]


def test_today_reusable_csv_path_picks_latest_mtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    today = jobs.seoul_now().strftime("%Y%m%d")
    older = _write_csv(tmp_path, f"KOSPI_005930_Older_weekly_{today}.csv", close="74000")
    newer = _write_csv(tmp_path, f"KOSPI_005930_Newer_weekly_{today}.csv", close="76000")
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)

    assert jobs._today_reusable_csv_path("005930") == newer


def test_get_job_finalizes_analysis_file(
    client: TestClient,
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="finalize success")
        job = crud.create_job(db, ticker="005930", run_id=run.id)

    output_dir = tmp_path / "jobs" / str(job.id)
    _write_csv(output_dir, "005930_Samsung_weekly_20260421.csv")
    (output_dir / jobs.ANALYSIS_FILENAME).write_text(VALID_MARKDOWN, encoding="utf-8")
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)

    response = client.get(f"/api/jobs/{job.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["analysis_id"] is not None
    assert body["raw_markdown"] == VALID_MARKDOWN

    with test_db() as db:
        analysis = crud.get_analysis(db, body["analysis_id"])
        assert analysis is not None
        assert analysis.ticker == "005930"
        assert analysis.name == "Samsung"
        assert analysis.model == "claude-code"
        assert analysis.judgment == "매수"
        assert analysis.entry_price == 75000.0


def test_get_job_finalizes_when_pullback_is_valid_and_breakout_is_above_target(
    client: TestClient,
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="finalize mixed entry")
        job = crud.create_job(db, ticker="001540", run_id=run.id)

    output_dir = tmp_path / "jobs" / str(job.id)
    _write_csv(output_dir, "001540_AnGuk_weekly_20260522.csv", close="10730")
    (output_dir / jobs.ANALYSIS_FILENAME).write_text(MIXED_ENTRY_MARKDOWN, encoding="utf-8")
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)

    response = client.get(f"/api/jobs/{job.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["analysis_id"] is not None

    with test_db() as db:
        analysis = crud.get_analysis(db, body["analysis_id"])
        assert analysis is not None
        assert analysis.entry_price == 9600.0
        assert analysis.entry_price_max == 9775.0
        assert analysis.target_price == 11920.0


def test_get_job_refreshes_stock_price_after_finalizing_analysis(
    client: TestClient,
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="finalize refresh price")
        job = crud.create_job(db, ticker="005930", run_id=run.id)

    output_dir = tmp_path / "jobs" / str(job.id)
    _write_csv(output_dir, "005930_Samsung_weekly_20260421.csv")
    (output_dir / jobs.ANALYSIS_FILENAME).write_text(VALID_MARKDOWN, encoding="utf-8")
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)
    calls: list[str] = []

    def fake_fetch_and_store_latest_close(db: Session, ticker: str) -> object:
        calls.append(ticker)
        return crud.upsert_stock_price(
            db,
            ticker=ticker,
            price_date=date(2026, 5, 15),
            close_price=71500,
        )

    monkeypatch.setattr(
        jobs,
        "fetch_and_store_latest_close",
        fake_fetch_and_store_latest_close,
        raising=False,
    )

    response = client.get(f"/api/jobs/{job.id}")

    assert response.status_code == 200
    assert response.json()["status"] == "done"
    assert calls == ["005930"]

    with test_db() as db:
        stock_price = crud.get_stock_price(db, "005930")
        assert stock_price is not None
        assert stock_price.price_date == date(2026, 5, 15)
        assert stock_price.close_price == 71500


def test_get_job_keeps_done_when_price_refresh_fails(
    client: TestClient,
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="finalize price failure")
        job = crud.create_job(db, ticker="005930", run_id=run.id)

    output_dir = tmp_path / "jobs" / str(job.id)
    _write_csv(output_dir, "005930_Samsung_weekly_20260421.csv")
    (output_dir / jobs.ANALYSIS_FILENAME).write_text(VALID_MARKDOWN, encoding="utf-8")
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)
    calls: list[str] = []

    def fail_fetch_and_store_latest_close(db: Session, ticker: str) -> object:
        calls.append(ticker)
        raise RuntimeError("price source unavailable")

    monkeypatch.setattr(
        jobs,
        "fetch_and_store_latest_close",
        fail_fetch_and_store_latest_close,
        raising=False,
    )

    response = client.get(f"/api/jobs/{job.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["analysis_id"] is not None
    assert calls == ["005930"]

    with test_db() as db:
        saved_job = crud.get_job(db, job.id)
        assert saved_job is not None
        assert saved_job.status == "done"
        assert saved_job.analysis_id == body["analysis_id"]


def test_get_job_finalizes_with_db_stock_name_when_csv_name_missing(
    client: TestClient,
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        db.add(KrxStock(code="129920", name="대성하이텍", name_initials="ㄷㅅㅎㅇㅌ", updated_at=seoul_now()))
        db.commit()
        run = crud.create_run(db, memo="finalize db stock name")
        job = crud.create_job(db, ticker="129920", run_id=run.id)

    output_dir = tmp_path / "jobs" / str(job.id)
    output_dir.mkdir(parents=True)
    (output_dir / "129920_weekly_20260514.csv").write_text(
        "ticker,name,close\n129920,,10540\n",
        encoding="utf-8-sig",
    )
    (output_dir / jobs.ANALYSIS_FILENAME).write_text(VALID_MARKDOWN, encoding="utf-8")
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)

    response = client.get(f"/api/jobs/{job.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"

    with test_db() as db:
        analysis = crud.get_analysis(db, body["analysis_id"])
        assert analysis is not None
        assert analysis.ticker == "129920"
        assert analysis.name == "대성하이텍"


def test_finalize_analysis_file_is_idempotent_across_stale_sessions(
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="duplicate finalize")
        job = crud.create_job(db, ticker="005930", run_id=run.id)
        run_id = run.id
        job_id = job.id

    output_dir = tmp_path / "jobs" / str(job_id)
    _write_csv(output_dir, "005930_Samsung_weekly_20260421.csv")
    (output_dir / jobs.ANALYSIS_FILENAME).write_text(VALID_MARKDOWN, encoding="utf-8")
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)

    db1 = test_db()
    db2 = test_db()
    try:
        job1 = crud.get_job(db1, job_id)
        job2 = crud.get_job(db2, job_id)
        assert job1 is not None
        assert job2 is not None
        assert job1.status == "pending"
        assert job2.status == "pending"

        jobs._finalize_pending_job_if_ready(db1, job1)
        jobs._finalize_pending_job_if_ready(db2, job2)
    finally:
        db1.close()
        db2.close()

    with test_db() as db:
        analyses = crud.get_analyses_by_run(db, run_id)
        saved_job = crud.get_job(db, job_id)
        assert saved_job is not None
        assert saved_job.status == "done"
        assert len(analyses) == 1
        assert analyses[0].id == saved_job.analysis_id


def test_get_job_finalizes_us_analysis_without_zero_padding(
    client: TestClient,
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="us finalize success")
        job = crud.create_job(db, ticker="AAPL", run_id=run.id)

    output_dir = tmp_path / "jobs" / str(job.id)
    output_dir.mkdir(parents=True)
    (output_dir / "AAPL_Apple Inc_weekly_20260422.csv").write_text(
        "ticker,name,close\nAAPL,Apple Inc,266.17\n",
        encoding="utf-8-sig",
    )
    (output_dir / jobs.ANALYSIS_FILENAME).write_text(VALID_MARKDOWN, encoding="utf-8")
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)

    response = client.get(f"/api/jobs/{job.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"

    with test_db() as db:
        analysis = crud.get_analysis(db, body["analysis_id"])
        assert analysis is not None
        assert analysis.ticker == "AAPL"
        assert analysis.name == "Apple Inc"


def test_list_jobs_finalizes_pending_analysis_file(
    client: TestClient,
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="list finalize")
        job = crud.create_job(db, ticker="036800", run_id=run.id, model="codex")
        run_id = run.id

    output_dir = tmp_path / "jobs" / str(job.id)
    _write_csv(output_dir, "036800_나이스정보통신_weekly_20260422.csv", close="36350")
    (output_dir / jobs.ANALYSIS_FILENAME).write_text(VALID_MARKDOWN, encoding="utf-8")
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)

    response = client.get(f"/api/jobs?run_id={run_id}")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["status"] == "done"

    with test_db() as db:
        analysis = crud.get_analysis(db, body[0]["analysis_id"])
        assert analysis is not None
        assert analysis.name == "나이스정보통신"
        assert analysis.model == "codex-cli"


def test_list_jobs_pending_filter_excludes_job_finalized_to_done(
    client: TestClient,
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="pending filter after finalize")
        job = crud.create_job(db, ticker="005930", run_id=run.id)
        job_id = job.id

    output_dir = tmp_path / "jobs" / str(job_id)
    _write_csv(output_dir, "005930_Samsung_weekly_20260421.csv")
    (output_dir / jobs.ANALYSIS_FILENAME).write_text(VALID_MARKDOWN, encoding="utf-8")
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)

    response = client.get("/api/jobs?status=pending")

    assert response.status_code == 200
    assert response.json() == []

    with test_db() as db:
        saved_job = crud.get_job(db, job_id)
        assert saved_job is not None
        assert saved_job.status == "done"


def test_list_jobs_done_filter_includes_job_finalized_from_pending(
    client: TestClient,
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="done filter after finalize")
        job = crud.create_job(db, ticker="005930", run_id=run.id)
        job_id = job.id

    output_dir = tmp_path / "jobs" / str(job_id)
    _write_csv(output_dir, "005930_Samsung_weekly_20260421.csv")
    (output_dir / jobs.ANALYSIS_FILENAME).write_text(VALID_MARKDOWN, encoding="utf-8")
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)

    response = client.get("/api/jobs?status=done")

    assert response.status_code == 200
    body = response.json()
    assert [job["id"] for job in body] == [job_id]
    assert body[0]["status"] == "done"
    assert body[0]["analysis_id"] is not None


def test_stock_name_from_csv_filename_allows_names_with_underscores() -> None:
    csv_path = Path("005930_Samsung_Electronics_weekly_20260422.csv")

    assert jobs._stock_name_from_csv_filename(csv_path, "005930") == "Samsung_Electronics"


def test_stock_name_from_csv_filename_ignores_market_prefix() -> None:
    csv_path = Path("005930_KOSPI_Samsung_Electronics_weekly_20260422.csv")

    assert jobs._stock_name_from_csv_filename(csv_path, "005930") == "Samsung_Electronics"


def test_stock_name_from_csv_filename_supports_market_first_prefix() -> None:
    csv_path = Path("KOSPI_005930_Samsung_Electronics_weekly_20260422.csv")

    assert jobs._stock_name_from_csv_filename(csv_path, "005930") == "Samsung_Electronics"


def test_stock_name_from_csv_filename_supports_us_market_first_prefix() -> None:
    csv_path = Path("NASDAQ_AAPL_Apple Inc_weekly_20260422.csv")

    assert jobs._stock_name_from_csv_filename(csv_path, "AAPL") == "Apple Inc"


def test_get_job_keeps_pending_before_timeout(
    client: TestClient,
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="pending before timeout")
        job = crud.create_job(db, ticker="005930", run_id=run.id)

    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)

    response = client.get(f"/api/jobs/{job.id}")

    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_get_job_marks_timeout_after_result_deadline(
    client: TestClient,
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="timeout")
        job = crud.create_job(db, ticker="005930", run_id=run.id)
        job_id = job.id
        saved_job = crud.get_job(db, job.id)
        assert saved_job is not None
        saved_job.created_at = seoul_now() - timedelta(seconds=jobs.ANALYSIS_RESULT_TIMEOUT_SECONDS + 1)
        db.commit()

    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)

    response = client.get(f"/api/jobs/{job_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_message"].startswith("timeout:")


def test_get_job_marks_model_exit_when_process_finishes_without_analysis(
    client: TestClient,
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="model exit")
        job = crud.create_job(db, ticker="005930", run_id=run.id, model="gemini")

    output_dir = tmp_path / "jobs" / str(job.id)
    output_dir.mkdir(parents=True)
    (output_dir / jobs.EXIT_CODE_FILENAME).write_text("1", encoding="utf-8")
    (output_dir / jobs.STDERR_LOG_FILENAME).write_text("Gemini CLI update failed", encoding="utf-8")
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)

    response = client.get(f"/api/jobs/{job.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_message"].startswith("model_exit: gemini: exit_code=1")
    assert "Gemini CLI update failed" in body["error_message"]


def test_get_job_marks_model_start_failure_when_pid_file_missing(
    client: TestClient,
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="missing pid")
        job = crud.create_job(db, ticker="005930", run_id=run.id, model="gemini")
        job_id = job.id
        saved_job = crud.get_job(db, job_id)
        assert saved_job is not None
        saved_job.created_at = seoul_now() - timedelta(seconds=jobs.MODEL_START_GRACE_SECONDS + 1)
        db.commit()

    output_dir = tmp_path / "jobs" / str(job_id)
    output_dir.mkdir(parents=True)
    (output_dir / jobs.PROMPT_FILENAME).write_text("prompt", encoding="utf-8")
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)

    response = client.get(f"/api/jobs/{job_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_message"].startswith("model_start: gemini: pid file was not created")


def test_get_job_saves_raw_markdown_on_parse_failure(
    client: TestClient,
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="parser failure")
        job = crud.create_job(db, ticker="005930", run_id=run.id)

    output_dir = tmp_path / "jobs" / str(job.id)
    _write_csv(output_dir, "005930_Samsung_weekly_20260421.csv")
    bad_markdown = "## 분석\n- 추세: 상승\n판정 없음"
    (output_dir / jobs.ANALYSIS_FILENAME).write_text(bad_markdown, encoding="utf-8")
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)

    response = client.get(f"/api/jobs/{job.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["raw_markdown"] == bad_markdown
    assert body["error_message"].startswith("parser:")


def test_get_job_rejects_inconsistent_price_scenario(
    client: TestClient,
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="price consistency failure")
        job = crud.create_job(db, ticker="291650", run_id=run.id)

    output_dir = tmp_path / "jobs" / str(job.id)
    _write_csv(output_dir, "291650_Aptamer_weekly_20260421.csv", close="1707")
    (output_dir / jobs.ANALYSIS_FILENAME).write_text(INVALID_PRICE_MARKDOWN, encoding="utf-8")
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)

    response = client.get(f"/api/jobs/{job.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["raw_markdown"] == INVALID_PRICE_MARKDOWN
    assert "price_consistency" in body["error_message"]


def test_run_analysis_pipeline_marks_pick_failure(
    test_db: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="pipeline failure")
        job = crud.create_job(db, ticker="005930", run_id=run.id)

    monkeypatch.setattr(jobs, "SessionLocal", test_db)
    monkeypatch.setattr(jobs, "_resolve_stock_name", lambda db, ticker: "Samsung")

    def fail_pick(ticker: str, stock_name: str, output_dir: Path) -> None:
        raise ValueError("종목 데이터 없음: 005930")

    monkeypatch.setattr(jobs, "_run_pick", fail_pick)

    run_analysis_pipeline(job.id)

    with test_db() as db:
        saved_job = crud.get_job(db, job.id)
        assert saved_job is not None
        assert saved_job.status == "failed"
        assert saved_job.error_message == "pick: 종목 데이터 없음: 005930"


def test_run_analysis_pipeline_marks_model_start_failure(
    test_db: sessionmaker[Session],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with test_db() as db:
        run = crud.create_run(db, memo="model start failure")
        job = crud.create_job(db, ticker="005930", run_id=run.id)

    monkeypatch.setattr(jobs, "SessionLocal", test_db)
    monkeypatch.setattr(jobs, "PICK_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(jobs, "_resolve_stock_name", lambda db, ticker: "Samsung")

    def fake_pick(ticker: str, stock_name: str, output_dir: Path) -> None:
        _write_csv(output_dir, "KOSPI_005930_Samsung_weekly_20260507.csv")

    monkeypatch.setattr(jobs, "_run_pick", fake_pick)

    def fail_claude(*args: object) -> FakeProcess:
        raise FileNotFoundError("claude")

    monkeypatch.setattr(jobs, "_run_claude", fail_claude)

    run_analysis_pipeline(job.id)

    with test_db() as db:
        saved_job = crud.get_job(db, job.id)
        assert saved_job is not None
        assert saved_job.status == "failed"
        assert saved_job.error_message == "model_start: claude: claude"


def test_run_claude_writes_prompt_file_and_starts_popen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(jobs.subprocess, "Popen", fake_popen)

    prompt_path = tmp_path / "prompt.md"
    stdout_path = tmp_path / "stdout.log"
    stderr_path = tmp_path / "stderr.log"
    analysis_path = tmp_path / "analysis.md"
    pid_path = tmp_path / "model.pid"
    exit_code_path = tmp_path / "exit_code.txt"

    process = jobs._run_claude(
        "ticker,name,close\n005930,Samsung,75000\n",
        jobs.SYSTEM_PROMPT,
        analysis_path,
        prompt_path,
        stdout_path,
        stderr_path,
        pid_path,
        exit_code_path,
    )

    assert process.pid == 1234
    assert captured["args"][0].endswith("python.exe") or captured["args"][0].endswith("python")
    assert captured["args"][1] == "-c"
    assert prompt_path.exists()
    assert pid_path.read_text(encoding="utf-8") == "1234"
    prompt = prompt_path.read_text(encoding="utf-8")
    assert "005930" in prompt
    assert str(analysis_path.resolve()) in prompt
    payload = json.loads(captured["args"][3])
    assert "--dangerously-skip-permissions" in payload["cmd"]
    assert "--model" in payload["cmd"]
    assert "sonnet" in payload["cmd"]
    assert "-p" in payload["cmd"]
    assert payload["prompt_path"] == str(prompt_path.resolve())
    assert payload["stdout_path"] == str(stdout_path.resolve())
    assert payload["stderr_path"] == str(stderr_path.resolve())
    assert payload["exit_code_path"] == str(exit_code_path.resolve())
    assert captured["stdin"] == jobs.subprocess.DEVNULL
    assert captured["stdout"] == jobs.subprocess.DEVNULL
    assert captured["stderr"] == jobs.subprocess.DEVNULL


def test_run_codex_passes_yolo_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(jobs.subprocess, "Popen", fake_popen)

    jobs._run_codex(
        "ticker,name,close\n005930,Samsung,75000\n",
        jobs.SYSTEM_PROMPT,
        tmp_path / "analysis.md",
        tmp_path / "prompt.md",
        tmp_path / "stdout.log",
        tmp_path / "stderr.log",
        tmp_path / "model.pid",
        tmp_path / "exit_code.txt",
    )

    payload = json.loads(captured["args"][3])
    assert payload["cmd"][1:4] == ["exec", "--yolo", "-"]


def test_codex_cmd_prefers_current_windows_native_exe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    npm_root = (
        tmp_path
        / "AppData"
        / "Roaming"
        / "npm"
        / "node_modules"
        / "@openai"
        / "codex"
        / "node_modules"
        / "@openai"
    )
    native_exe = (
        npm_root
        / "codex-win32-x64"
        / "vendor"
        / "x86_64-pc-windows-msvc"
        / "bin"
        / "codex.exe"
    )
    native_exe.parent.mkdir(parents=True)
    native_exe.write_text("", encoding="utf-8")

    monkeypatch.setattr(jobs.sys, "platform", "win32")
    monkeypatch.setattr(jobs.Path, "home", lambda: tmp_path)

    assert jobs._codex_cmd() == [str(native_exe), "exec", "--yolo", "-"]


def test_run_codex_writes_full_csv_to_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_popen(args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(jobs.subprocess, "Popen", fake_popen)

    csv_text = "ticker,name,close\n" + "\n".join(
        f"005930,Samsung,{price}" for price in range(300)
    )
    prompt_path = tmp_path / "prompt.md"

    jobs._run_codex(
        csv_text,
        jobs.SYSTEM_PROMPT,
        tmp_path / "analysis.md",
        prompt_path,
        tmp_path / "stdout.log",
        tmp_path / "stderr.log",
        tmp_path / "model.pid",
        tmp_path / "exit_code.txt",
    )

    prompt = prompt_path.read_text(encoding="utf-8")
    assert "005930,Samsung,0" in prompt
    assert "005930,Samsung,299" in prompt


def test_file_output_prompt_identifies_last_real_week_before_future_cloud_rows(
    tmp_path: Path,
) -> None:
    csv_text = "\n".join(
        [
            "date,ticker,name,open,high,low,close,volume,ma20,ma60,ma120,ichi_conv,ichi_base,cloud_top,cloud_bottom",
            "2026-05-11,003010,혜인,7330,7350,6170,6230,1899763,5776,5422,5373,7015,6830,5484,5225",
            "2026-05-18,003010,혜인,6120,6180,5530,6040,1294957,5810,5443,5377,7015,6830,5427,5225",
            "2026-05-25,003010,혜인,,,,,,,,,,,,5427,5225",
        ]
    )

    prompt = jobs._build_file_output_prompt(
        jobs.SYSTEM_PROMPT,
        csv_text,
        tmp_path / "analysis.md",
    )

    assert "분석 기준 행: 2026-05-18" in prompt
    assert "close=6040" in prompt
    assert "ma20=5810" in prompt
    assert "미래 구름 행(OHLC 빈 행)을 현재가 분석 기준으로 사용하지 마세요." in prompt


def test_run_gemini_passes_yolo_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(jobs.subprocess, "Popen", fake_popen)

    jobs._run_gemini(
        "ticker,name,close\n005930,Samsung,75000\n",
        jobs.SYSTEM_PROMPT,
        tmp_path / "analysis.md",
        tmp_path / "prompt.md",
        tmp_path / "stdout.log",
        tmp_path / "stderr.log",
        tmp_path / "model.pid",
        tmp_path / "exit_code.txt",
    )

    payload = json.loads(captured["args"][3])
    assert "--yolo" in payload["cmd"]
    yolo_idx = payload["cmd"].index("--yolo")
    assert payload["cmd"][yolo_idx + 1 : yolo_idx + 4] == ["-p", "", "--output-format"]
