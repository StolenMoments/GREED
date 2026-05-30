from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.models import BacktestRun, BacktestSignal, BacktestStat
from backend.routers.backtest import router


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
    app.include_router(router)

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


def _seed(db: Session) -> int:
    run = BacktestRun(
        created_at=datetime(2026, 5, 24, 9, 0, 0),
        universe="KOSPI200",
        buy_threshold=4,
        horizons="4,8,12,26",
        warmup_weeks=120,
        data_start=date(2015, 1, 5),
        data_end=date(2026, 5, 18),
        ticker_count=2,
        signal_count=2,
        notes=None,
        source_analysis_id=42,
        strategy_kind="analysis_similarity",
        similarity_threshold=9,
    )
    db.add(run)
    db.flush()
    db.add(
        BacktestStat(
            run_id=run.id,
            horizon=4,
            score_bucket="ALL",
            count=2,
            censored_count=0,
            win_rate=0.5,
            mean=0.01,
            median=0.01,
            std=0.05,
            p25=-0.02,
            p75=0.04,
            min=-0.04,
            max=0.06,
        )
    )
    db.add(
        BacktestSignal(
            run_id=run.id,
            ticker="005930",
            name="삼성전자",
            signal_date=date(2020, 1, 6),
            score=6,
            score_bucket="6-7",
            entry_date=date(2020, 1, 13),
            entry_price=10000.0,
            ret_4w=0.06,
            ret_8w=0.02,
            ret_12w=-0.04,
            ret_26w=None,
        )
    )
    db.add(
        BacktestSignal(
            run_id=run.id,
            ticker="000660",
            name="SK하이닉스",
            signal_date=date(2020, 2, 3),
            score=4,
            score_bucket="4-5",
            entry_date=date(2020, 2, 10),
            entry_price=50000.0,
            ret_4w=-0.04,
            ret_8w=0.01,
            ret_12w=0.03,
            ret_26w=0.12,
        )
    )
    db.commit()
    return run.id


def test_list_runs(client: TestClient, db_session: Session) -> None:
    run_id = _seed(db_session)
    resp = client.get("/api/backtest/runs")
    assert resp.status_code == 200
    data = resp.json()
    run = next(r for r in data if r["id"] == run_id)
    assert run["source_analysis_id"] == 42
    assert run["strategy_kind"] == "analysis_similarity"
    assert run["similarity_threshold"] == 9


def test_run_detail_includes_stats(client: TestClient, db_session: Session) -> None:
    run_id = _seed(db_session)
    resp = client.get(f"/api/backtest/runs/{run_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["universe"] == "KOSPI200"
    assert body["source_analysis_id"] == 42
    assert body["strategy_kind"] == "analysis_similarity"
    assert body["similarity_threshold"] == 9
    assert any(s["horizon"] == 4 and s["score_bucket"] == "ALL" for s in body["stats"])


def test_contract_run_detail_includes_event_summary(client: TestClient, db_session: Session) -> None:
    run = BacktestRun(
        created_at=datetime(2026, 5, 24, 9, 0, 0),
        universe="KOSPI200",
        buy_threshold=10,
        horizons="contract",
        warmup_weeks=120,
        data_start=date(2015, 1, 5),
        data_end=date(2026, 5, 18),
        ticker_count=2,
        signal_count=5,
        notes=None,
        source_analysis_id=42,
        strategy_kind="analysis_contract",
        similarity_threshold=10,
    )
    db_session.add(run)
    db_session.flush()
    db_session.add_all(
        [
            BacktestSignal(
                run_id=run.id,
                ticker="005930",
                name="Samsung",
                signal_date=date(2024, 1, 2),
                score=12,
                score_bucket="12",
                entry_date=date(2024, 1, 3),
                entry_price=100,
                exit_date=date(2024, 1, 10),
                exit_reason="target",
                exit_price=110,
                event_return=0.10,
                days_held=5,
            ),
            BacktestSignal(
                run_id=run.id,
                ticker="000660",
                name="SK Hynix",
                signal_date=date(2024, 1, 2),
                score=10,
                score_bucket="10",
                entry_date=date(2024, 1, 3),
                entry_price=100,
                exit_date=date(2024, 1, 8),
                exit_reason="stop",
                exit_price=95,
                event_return=-0.05,
                days_held=3,
            ),
            BacktestSignal(
                run_id=run.id,
                ticker="035420",
                name="Naver",
                signal_date=date(2024, 1, 2),
                score=11,
                score_bucket="11",
                entry_date=date(2024, 1, 4),
                entry_price=100,
                exit_date=date(2024, 2, 2),
                exit_reason="expiry",
                exit_price=103,
                event_return=0.03,
                days_held=20,
            ),
            BacktestSignal(
                run_id=run.id,
                ticker="068270",
                name="Celltrion",
                signal_date=date(2024, 1, 2),
                score=11,
                score_bucket="11",
                entry_date=date(2024, 1, 5),
                entry_price=100,
                exit_date=date(2024, 2, 2),
                exit_reason="expiry",
                exit_price=98,
                event_return=-0.02,
                days_held=19,
            ),
            BacktestSignal(
                run_id=run.id,
                ticker="051910",
                name="LG Chem",
                signal_date=date(2024, 1, 2),
                score=11,
                score_bucket="11",
                entry_date=None,
                entry_price=100,
                exit_reason="no_entry",
            ),
        ]
    )
    db_session.commit()

    resp = client.get(f"/api/backtest/runs/{run.id}")

    assert resp.status_code == 200
    summary = resp.json()["event_summary"]
    assert summary["signal_count"] == 5
    assert summary["entered_count"] == 4
    assert summary["no_entry_count"] == 1
    assert summary["target_count"] == 1
    assert summary["stop_count"] == 1
    assert summary["expiry_count"] == 2
    assert summary["target_hit_rate"] == pytest.approx(1 / 4)
    assert summary["positive_return_rate"] == pytest.approx(2 / 4)
    assert summary["win_rate"] == pytest.approx(summary["target_hit_rate"])
    assert summary["mean_return"] == pytest.approx(0.015)
    assert summary["avg_days_held"] == pytest.approx(11.75)


def test_signals_filter_by_bucket(client: TestClient, db_session: Session) -> None:
    run_id = _seed(db_session)
    resp = client.get(f"/api/backtest/runs/{run_id}/signals", params={"score_bucket": "6-7"})
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 1
    assert page["items"][0]["ticker"] == "005930"


def test_histogram_returns_bins_for_horizon(client: TestClient, db_session: Session) -> None:
    run_id = _seed(db_session)
    resp = client.get(
        f"/api/backtest/runs/{run_id}/histogram",
        params={"horizon": 4, "score_bucket": "ALL", "bins": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["horizon"] == 4
    assert body["score_bucket"] == "ALL"
    assert sum(bin_["count"] for bin_ in body["bins"]) == 2


def test_run_detail_404(client: TestClient) -> None:
    resp = client.get("/api/backtest/runs/999999")
    assert resp.status_code == 404
