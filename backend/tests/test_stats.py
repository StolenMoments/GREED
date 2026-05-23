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
    ticker: str = "005930",
    cloud_position: str = "구름 위",
    ma_alignment: str = "정배열",
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
        ticker=ticker,
        name="테스트종목",
        name_initials="",
        model=model,
        markdown="",
        judgment=judgment,
        trend="상승",
        cloud_position=cloud_position,
        ma_alignment=ma_alignment,
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


# ---------------------------------------------------------------------------
# head-to-head
# ---------------------------------------------------------------------------

def test_head_to_head_no_run_id(client: TestClient) -> None:
    """run_id 없으면 빈 응답."""
    resp = client.get("/api/stats/head-to-head")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tickers"] == 0
    assert data["matrix"] == []
    assert data["agreement"] == {}


def test_head_to_head_empty_run(client: TestClient, db_session: Session) -> None:
    """분석이 0건인 run → 빈 응답."""
    run = _make_run(db_session)
    db_session.commit()

    resp = client.get(f"/api/stats/head-to-head?run_id={run.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == run.id
    assert data["tickers"] == 0
    assert data["matrix"] == []
    assert data["agreement"] == {}


def test_head_to_head_two_models(client: TestClient, db_session: Session) -> None:
    """
    rule: AAAA=매수(목표달성, e=100 t=120 s=90), BBBB=매수(손절, e=100 t=120 s=90)
    claude: AAAA=매수(목표달성, e=100 t=120 s=90), BBBB=홀드

    손계산:
      공통 ticker: 2 (AAAA, BBBB)
      rule — buy=2, hits=1, stops=1, win_rate=0.5, expectancy=5.0
      claude — buy=1, hits=1, stops=0, win_rate=1.0, expectancy=20.0
      agreement: claude_and_rule=1 (AAAA), rule_only=1 (BBBB)
    """
    run = _make_run(db_session)
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    odate = date(2025, 2, 5)

    _make_analysis(db_session, run.id, "rule", "매수", ticker="AAAA",
                   outcome=OUTCOME_TARGET, outcome_date=odate,
                   entry_price=100, target_price=120, stop_loss=90, created_at=t0)
    _make_analysis(db_session, run.id, "rule", "매수", ticker="BBBB",
                   outcome=OUTCOME_STOP, outcome_date=odate,
                   entry_price=100, target_price=120, stop_loss=90, created_at=t0)
    _make_analysis(db_session, run.id, "claude", "매수", ticker="AAAA",
                   outcome=OUTCOME_TARGET, outcome_date=odate,
                   entry_price=100, target_price=120, stop_loss=90, created_at=t0)
    _make_analysis(db_session, run.id, "claude", "홀드", ticker="BBBB")
    db_session.commit()

    resp = client.get(f"/api/stats/head-to-head?run_id={run.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == run.id
    assert data["tickers"] == 2

    matrix = {row["model"]: row for row in data["matrix"]}
    assert matrix["rule"]["buy"] == 2
    assert matrix["rule"]["hits"] == 1
    assert matrix["rule"]["stops"] == 1
    assert matrix["rule"]["expectancy_pct"] == pytest.approx(5.0)

    assert matrix["claude"]["buy"] == 1
    assert matrix["claude"]["hits"] == 1
    assert matrix["claude"]["stops"] == 0
    assert matrix["claude"]["expectancy_pct"] == pytest.approx(20.0)

    agreement = data["agreement"]
    assert agreement.get("claude_and_rule") == 1
    assert agreement.get("rule_only") == 1


def test_head_to_head_single_model(client: TestClient, db_session: Session) -> None:
    """모델이 1개면 교집합 = 해당 모델 전체 ticker."""
    run = _make_run(db_session)
    _make_analysis(db_session, run.id, "rule", "매수", ticker="AAAA")
    _make_analysis(db_session, run.id, "rule", "홀드", ticker="BBBB")
    db_session.commit()

    resp = client.get(f"/api/stats/head-to-head?run_id={run.id}")
    data = resp.json()
    assert data["tickers"] == 2
    assert len(data["matrix"]) == 1
    assert data["matrix"][0]["model"] == "rule"
    assert data["matrix"][0]["buy"] == 1
    assert data["agreement"] == {"rule_only": 1}


# ---------------------------------------------------------------------------
# by-signal
# ---------------------------------------------------------------------------

def test_by_signal_basic(client: TestClient, db_session: Session) -> None:
    """
    (구름 위, 정배열) × 2 — 1 목표달성 + 1 손절 → win_rate=0.5, expectancy=5.0
    (구름 아래, 역배열) × 1 — 1 목표달성 → win_rate=1.0, expectancy=20.0
    """
    run = _make_run(db_session)
    t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    odate = date(2025, 2, 5)

    for outcome in (OUTCOME_TARGET, OUTCOME_STOP):
        _make_analysis(db_session, run.id, "rule", "매수",
                       cloud_position="구름 위", ma_alignment="정배열",
                       outcome=outcome, outcome_date=odate,
                       entry_price=100, target_price=120, stop_loss=90, created_at=t0)
    _make_analysis(db_session, run.id, "rule", "매수",
                   cloud_position="구름 아래", ma_alignment="역배열",
                   outcome=OUTCOME_TARGET, outcome_date=odate,
                   entry_price=100, target_price=120, stop_loss=90, created_at=t0)
    db_session.commit()

    resp = client.get("/api/stats/by-signal?model=rule")
    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "rule"

    cells = {(c["cloud_position"], c["ma_alignment"]): c for c in data["cells"]}

    top = cells[("구름 위", "정배열")]
    assert top["count"] == 2
    assert top["win_rate"] == pytest.approx(0.5)
    assert top["expectancy_pct"] == pytest.approx(5.0)

    bottom = cells[("구름 아래", "역배열")]
    assert bottom["count"] == 1
    assert bottom["win_rate"] == pytest.approx(1.0)
    assert bottom["expectancy_pct"] == pytest.approx(20.0)


def test_by_signal_no_terminal_outcomes(client: TestClient, db_session: Session) -> None:
    """매수이지만 진행중이면 win_rate=null."""
    run = _make_run(db_session)
    _make_analysis(db_session, run.id, "claude", "매수",
                   cloud_position="구름 위", ma_alignment="정배열",
                   outcome=OUTCOME_ONGOING)
    db_session.commit()

    resp = client.get("/api/stats/by-signal?model=claude")
    data = resp.json()
    cells = {(c["cloud_position"], c["ma_alignment"]): c for c in data["cells"]}
    cell = cells[("구름 위", "정배열")]
    assert cell["count"] == 1
    assert cell["win_rate"] is None
    assert cell["expectancy_pct"] is None


def test_by_signal_empty_model(client: TestClient, db_session: Session) -> None:
    """존재하지 않는 모델 → cells=[]."""
    resp = client.get("/api/stats/by-signal?model=unknown")
    assert resp.status_code == 200
    data = resp.json()
    assert data["model"] == "unknown"
    assert data["cells"] == []
