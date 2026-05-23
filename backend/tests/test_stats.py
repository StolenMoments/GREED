from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.models import Analysis, Run
from backend.outcome import OUTCOME_ONGOING, OUTCOME_STOP, OUTCOME_TARGET
from backend.routers.stats import router


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


def _make_run(db: Session) -> Run:
    run = Run(memo="test run")
    db.add(run)
    db.flush()
    return run


def _make_analysis(
    db: Session,
    run_id: int,
    model: str,
    judgment: str,
    outcome: str | None = None,
    outcome_date: date | None = None,
    entry_price: float | None = None,
    target_price: float | None = None,
    stop_loss: float | None = None,
    created_at: datetime | None = None,
) -> Analysis:
    created = created_at or datetime(2025, 1, 1, tzinfo=timezone.utc)
    a = Analysis(
        run_id=run_id,
        ticker="005930",
        name="테스트종목",
        name_initials="",
        model=model,
        markdown="",
        judgment=judgment,
        trend="상승",
        cloud_position="구름 위",
        ma_alignment="정배열",
        entry_price=entry_price,
        target_price=target_price,
        stop_loss=stop_loss,
        outcome=outcome,
        outcome_date=outcome_date,
        created_at=created,
    )
    db.add(a)
    db.flush()
    return a


def test_empty_db_returns_empty_list(client: TestClient) -> None:
    resp = client.get("/api/stats/by-model")
    assert resp.status_code == 200
    assert resp.json() == []


def test_by_model_win_rate_and_expectancy(client: TestClient, db_session: Session) -> None:
    """
    rule 모델:
      매수+목표달성: entry=100, target=120, stop=90  → gain=20%, loss=10%
      매수+손절:    entry=100, target=120, stop=90  → gain=20%, loss=10%
      매도 (prices absent): 집계 무관

    손계산:
      win_rate = 1/(1+1) = 0.5
      avg_gain = 20.0
      avg_loss = 10.0
      expectancy = 0.5*20 - 0.5*10 = 5.0
    """
    run = _make_run(db_session)
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    outcome_dt = date(2025, 2, 5)  # 35 days later → 5 weeks

    _make_analysis(
        db_session, run.id, "rule", "매수",
        outcome=OUTCOME_TARGET, outcome_date=outcome_dt,
        entry_price=100, target_price=120, stop_loss=90,
        created_at=t0,
    )
    _make_analysis(
        db_session, run.id, "rule", "매수",
        outcome=OUTCOME_STOP, outcome_date=outcome_dt,
        entry_price=100, target_price=120, stop_loss=90,
        created_at=t0,
    )
    _make_analysis(
        db_session, run.id, "rule", "매도",
        outcome=None,
    )
    db_session.commit()

    resp = client.get("/api/stats/by-model")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1

    stat = data[0]
    assert stat["model"] == "rule"
    assert stat["total"] == 3
    assert stat["judgments"] == {"매수": 2, "매도": 1}
    assert stat["outcomes"] == {OUTCOME_TARGET: 1, OUTCOME_STOP: 1}

    assert stat["win_rate"] == pytest.approx(0.5)
    assert stat["expectancy_pct"] == pytest.approx(5.0)
    assert stat["avg_holding_weeks"] == pytest.approx(35 / 7)


def test_by_model_no_terminal_outcomes_returns_null_win_rate(
    client: TestClient, db_session: Session
) -> None:
    """매수이지만 outcome이 진행중이면 win_rate는 null."""
    run = _make_run(db_session)
    _make_analysis(
        db_session, run.id, "claude", "매수",
        outcome=OUTCOME_ONGOING,
        entry_price=100, target_price=120, stop_loss=90,
    )
    db_session.commit()

    resp = client.get("/api/stats/by-model")
    stat = resp.json()[0]
    assert stat["win_rate"] is None
    assert stat["expectancy_pct"] is None


def test_by_model_null_prices_excluded_from_expectancy(
    client: TestClient, db_session: Session
) -> None:
    """entry/target/stop 중 하나라도 null이면 해당 분석은 집계 제외."""
    run = _make_run(db_session)
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    outcome_dt = date(2025, 2, 5)

    # prices all set → counts
    _make_analysis(
        db_session, run.id, "rule", "매수",
        outcome=OUTCOME_TARGET, outcome_date=outcome_dt,
        entry_price=100, target_price=120, stop_loss=90,
        created_at=t0,
    )
    # target_price=None → excluded from win_rate calc
    _make_analysis(
        db_session, run.id, "rule", "매수",
        outcome=OUTCOME_TARGET, outcome_date=outcome_dt,
        entry_price=100, target_price=None, stop_loss=90,
        created_at=t0,
    )
    db_session.commit()

    resp = client.get("/api/stats/by-model")
    stat = resp.json()[0]
    # only 1 valid analysis counted → denom=1, win_rate=1.0
    assert stat["win_rate"] == pytest.approx(1.0)
    assert stat["total"] == 2


def test_by_model_multiple_models(client: TestClient, db_session: Session) -> None:
    """여러 모델이 각각 별도 항목으로 반환된다."""
    run = _make_run(db_session)
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    outcome_dt = date(2025, 2, 5)

    for model in ("claude", "rule", "gemini"):
        _make_analysis(
            db_session, run.id, model, "매수",
            outcome=OUTCOME_TARGET, outcome_date=outcome_dt,
            entry_price=100, target_price=120, stop_loss=90,
            created_at=t0,
        )
    db_session.commit()

    resp = client.get("/api/stats/by-model")
    assert resp.status_code == 200
    models = [s["model"] for s in resp.json()]
    assert sorted(models) == ["claude", "gemini", "rule"]
