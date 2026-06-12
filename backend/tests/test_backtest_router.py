from __future__ import annotations

import json
from collections.abc import Generator
from datetime import date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from scripts.backtest.preload_daily import PreloadDailyResult
from scripts.backtest.preload_price_bars import PreloadPriceBarsResult

from backend.models import (
    Analysis,
    BacktestPreloadJob,
    BacktestRun,
    BacktestSignal,
    BacktestStat,
    BacktestStrategyJob,
    BacktestUniverseMember,
    DailyRallyCurrentCandidate,
    DailyRallyPatternStat,
    DailyRallyRuleStat,
    DailyRallyValidationSummary,
)
from backend.routers import backtest
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
    db_session.add(
        Analysis(
            id=42,
            run_id=7,
            ticker="005930",
            name="Samsung",
            model="claude",
            markdown="contract",
            judgment="buy",
            trend="up",
            cloud_position="above",
            ma_alignment="bullish",
            entry_price=100,
            target_price=115,
            stop_loss=94,
        )
    )
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
    assert summary["expectancy"] == pytest.approx(summary["mean_return"])
    assert summary["planned_target_return"] == pytest.approx(0.15)
    assert summary["planned_stop_return"] == pytest.approx(-0.06)
    assert summary["planned_risk_reward_ratio"] == pytest.approx(2.5)
    assert summary["avg_gain_return"] == pytest.approx(0.065)
    assert summary["avg_loss_return"] == pytest.approx(-0.035)
    assert summary["realized_payoff_ratio"] == pytest.approx(0.065 / 0.035)
    assert summary["avg_days_held"] == pytest.approx(11.75)

    breakdown = resp.json()["contract_breakdown"]
    assert breakdown["focus_threshold"] == 12
    assert breakdown["focus"]["signal_count"] == 1
    assert breakdown["focus"]["entered_count"] == 1
    assert breakdown["focus"]["target_count"] == 1
    assert breakdown["focus"]["mean_return"] == pytest.approx(0.10)
    assert breakdown["by_score"]["10"]["mean_return"] == pytest.approx(-0.05)
    assert breakdown["by_score"]["11"]["signal_count"] == 3
    assert breakdown["by_score"]["11"]["entered_count"] == 2
    assert breakdown["by_score"]["11"]["no_entry_count"] == 1
    assert breakdown["by_year"]["2024"]["signal_count"] == 5
    assert breakdown["by_year"]["2024"]["entered_count"] == 4
    assert breakdown["top_tickers"] == []
    assert breakdown["bottom_tickers"] == []


def test_span2_run_detail_includes_event_summary_with_open_count(
    client: TestClient,
    db_session: Session,
) -> None:
    run = BacktestRun(
        created_at=datetime(2026, 5, 24, 9, 0, 0),
        universe="KOSPI200-DB",
        buy_threshold=0,
        horizons="event",
        warmup_weeks=120,
        data_start=date(2024, 1, 1),
        data_end=date(2024, 2, 1),
        ticker_count=2,
        signal_count=2,
        strategy_kind="ichimoku_span2_breakout",
    )
    db_session.add(run)
    db_session.flush()
    db_session.add_all(
        [
            BacktestSignal(
                run_id=run.id,
                ticker="005930",
                name="Samsung",
                signal_date=date(2024, 1, 8),
                score=1,
                score_bucket="span2",
                entry_date=date(2024, 1, 8),
                entry_price=100,
                exit_date=date(2024, 1, 15),
                exit_reason="stop",
                exit_price=94,
                event_return=-0.06,
                days_held=7,
            ),
            BacktestSignal(
                run_id=run.id,
                ticker="000660",
                name="SK Hynix",
                signal_date=date(2024, 1, 22),
                score=1,
                score_bucket="span2",
                entry_date=date(2024, 1, 22),
                entry_price=100,
                exit_date=date(2024, 2, 5),
                exit_reason="open",
                exit_price=110,
                event_return=0.10,
                days_held=14,
            ),
        ]
    )
    db_session.commit()

    resp = client.get(f"/api/backtest/runs/{run.id}")

    assert resp.status_code == 200
    summary = resp.json()["event_summary"]
    assert summary["signal_count"] == 2
    assert summary["entered_count"] == 2
    assert summary["target_count"] == 0
    assert summary["stop_count"] == 1
    assert summary["open_count"] == 1
    assert summary["expiry_count"] == 0
    assert summary["no_entry_count"] == 0
    assert summary["positive_return_rate"] == pytest.approx(0.5)
    assert summary["win_rate"] == pytest.approx(summary["positive_return_rate"])
    assert summary["mean_return"] == pytest.approx(0.02)
    assert summary["avg_days_held"] == pytest.approx(10.5)


def test_create_strategy_job_rejects_duplicate_active_job(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called_job_ids: list[int] = []
    monkeypatch.setattr(
        backtest,
        "run_backtest_strategy_pipeline",
        lambda job_id: called_job_ids.append(job_id),
    )

    first = client.post(
        "/api/backtest/strategy-jobs",
        json={"strategy_kind": "ichimoku_span2_breakout"},
    )
    second = client.post(
        "/api/backtest/strategy-jobs",
        json={"strategy_kind": "ichimoku_span2_breakout"},
    )

    assert first.status_code == 202
    assert first.json()["status"] == "pending"
    assert called_job_ids == [first.json()["id"]]
    assert second.status_code == 409
    assert "already running" in second.json()["detail"]
    jobs = list(db_session.scalars(backtest.select(BacktestStrategyJob)).all())
    assert len(jobs) == 1


def test_create_strategy_job_accepts_daily_rally_kind(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called_job_ids: list[int] = []
    monkeypatch.setattr(
        backtest,
        "run_backtest_strategy_pipeline",
        lambda job_id: called_job_ids.append(job_id),
    )

    resp = client.post(
        "/api/backtest/strategy-jobs",
        json={"strategy_kind": "daily_20d_40pct_rally"},
    )

    assert resp.status_code == 202
    assert resp.json()["strategy_kind"] == "daily_20d_40pct_rally"
    assert called_job_ids == [resp.json()["id"]]


def test_run_backtest_strategy_pipeline_marks_done_with_run_id(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = BacktestStrategyJob(strategy_kind="ichimoku_span2_breakout")
    db_session.add(job)
    db_session.commit()
    job_id = job.id

    class FakeResult:
        ticker_count = 1
        records = [
            backtest.SignalRecord(
                ticker="005930",
                name="Samsung",
                signal_date=date(2024, 1, 8),
                score=1,
                score_bucket="span2",
                entry_date=date(2024, 1, 8),
                entry_price=100,
                returns={},
                exit_date=date(2024, 1, 15),
                exit_reason="stop",
                exit_price=94,
                event_return=-0.06,
                days_held=7,
            )
        ]
        stats = []
        data_start = date(2024, 1, 1)
        data_end = date(2024, 1, 31)

    monkeypatch.setattr(backtest, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(backtest, "load_active_universe", lambda db: [("005930", "Samsung")])
    monkeypatch.setattr(
        backtest,
        "preload_price_bars",
        lambda db, universe: PreloadPriceBarsResult(processed=len(list(universe))),
    )
    monkeypatch.setattr(backtest, "run_span2_breakout_backtest", lambda db: FakeResult())

    backtest.run_backtest_strategy_pipeline(job_id)

    saved = db_session.get(BacktestStrategyJob, job_id)
    assert saved is not None
    assert saved.status == "done"
    assert saved.backtest_run_id is not None
    assert saved.completed_at is not None
    run = db_session.get(BacktestRun, saved.backtest_run_id)
    assert run is not None
    assert run.strategy_kind == "ichimoku_span2_breakout"
    assert run.horizons == "event"
    assert run.buy_threshold == 0


def test_run_backtest_strategy_pipeline_daily_rally_marks_done_with_run_id(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = BacktestStrategyJob(strategy_kind="daily_20d_40pct_rally")
    db_session.add(job)
    db_session.commit()
    job_id = job.id

    class FakeResult:
        ticker_count = 1

    monkeypatch.setattr(backtest, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(backtest, "load_active_universe", lambda db: [("005930", "Samsung")])
    monkeypatch.setattr(
        backtest,
        "preload_price_bars",
        lambda db, universe: PreloadPriceBarsResult(processed=len(list(universe))),
    )
    monkeypatch.setattr(backtest, "run_daily_rally_backtest", lambda db: FakeResult())
    monkeypatch.setattr(backtest, "persist_daily_rally_run", lambda db, result: 77)

    backtest.run_backtest_strategy_pipeline(job_id)

    saved = db_session.get(BacktestStrategyJob, job_id)
    assert saved is not None
    assert saved.status == "done"
    assert saved.backtest_run_id == 77
    assert saved.completed_at is not None


def test_run_backtest_strategy_pipeline_preloads_active_universe_before_span2(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_session.add_all(
        [
            BacktestUniverseMember(
                ticker="005930",
                name="Samsung",
                market="KR",
                active=True,
                sort_order=1,
                source="test",
            ),
            BacktestUniverseMember(
                ticker="000660",
                name="SK Hynix",
                market="KR",
                active=True,
                sort_order=2,
                source="test",
            ),
        ]
    )
    job = BacktestStrategyJob(strategy_kind="ichimoku_span2_breakout")
    db_session.add(job)
    db_session.commit()
    job_id = job.id
    calls: list[list[tuple[str, str]]] = []

    class FakeResult:
        ticker_count = 0
        records = []
        stats = []
        data_start = None
        data_end = None

    def fake_preload(db: Session, *, universe):
        calls.append(list(universe))
        return PreloadPriceBarsResult(processed=len(calls[-1]))

    monkeypatch.setattr(backtest, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(backtest, "preload_price_bars", fake_preload)
    monkeypatch.setattr(backtest, "run_span2_breakout_backtest", lambda db: FakeResult())

    backtest.run_backtest_strategy_pipeline(job_id)

    assert calls == [[("005930", "Samsung"), ("000660", "SK Hynix")]]
    saved = db_session.get(BacktestStrategyJob, job_id)
    assert saved is not None
    assert saved.status == "done"


def test_run_backtest_strategy_pipeline_daily_rally_fails_without_run_on_preload_failure(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_session.add(
        BacktestUniverseMember(
            ticker="047040",
            name="Daewoo E&C",
            market="KR",
            active=True,
            sort_order=1,
            source="test",
        )
    )
    job = BacktestStrategyJob(strategy_kind="daily_20d_40pct_rally")
    db_session.add(job)
    db_session.commit()
    job_id = job.id
    persisted: list[int] = []

    monkeypatch.setattr(backtest, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(
        backtest,
        "preload_price_bars",
        lambda db, universe: PreloadPriceBarsResult(
            failed=[("047040", "Daewoo E&C", "fetch failed")]
        ),
    )
    monkeypatch.setattr(
        backtest,
        "run_daily_rally_backtest",
        lambda db: (_ for _ in ()).throw(AssertionError("engine should not run")),
    )
    monkeypatch.setattr(
        backtest,
        "persist_daily_rally_run",
        lambda db, result: persisted.append(1),
    )

    backtest.run_backtest_strategy_pipeline(job_id)

    saved = db_session.get(BacktestStrategyJob, job_id)
    assert saved is not None
    assert saved.status == "failed"
    assert saved.backtest_run_id is None
    assert "047040 Daewoo E&C: fetch failed" in saved.error_message
    assert persisted == []
    assert db_session.query(BacktestRun).count() == 0


def test_run_backtest_strategy_pipeline_marks_failed(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = BacktestStrategyJob(strategy_kind="ichimoku_span2_breakout")
    db_session.add(job)
    db_session.commit()
    job_id = job.id

    monkeypatch.setattr(backtest, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(backtest, "load_active_universe", lambda db: [("005930", "Samsung")])
    monkeypatch.setattr(
        backtest,
        "preload_price_bars",
        lambda db, universe: PreloadPriceBarsResult(processed=len(list(universe))),
    )
    monkeypatch.setattr(
        backtest,
        "run_span2_breakout_backtest",
        lambda db: (_ for _ in ()).throw(RuntimeError("price data unavailable")),
    )

    backtest.run_backtest_strategy_pipeline(job_id)

    saved = db_session.get(BacktestStrategyJob, job_id)
    assert saved is not None
    assert saved.status == "failed"
    assert saved.error_message == "price data unavailable"
    assert saved.completed_at is not None


def test_signals_filter_by_bucket(client: TestClient, db_session: Session) -> None:
    run_id = _seed(db_session)
    resp = client.get(f"/api/backtest/runs/{run_id}/signals", params={"score_bucket": "6-7"})
    assert resp.status_code == 200
    page = resp.json()
    assert page["total"] == 1
    assert page["items"][0]["ticker"] == "005930"


def test_contract_breakdown_ranks_tickers_with_at_least_five_entries(
    client: TestClient,
    db_session: Session,
) -> None:
    run = BacktestRun(
        created_at=datetime(2026, 5, 24, 9, 0, 0),
        universe="KOSPI200",
        buy_threshold=12,
        horizons="contract",
        warmup_weeks=120,
        data_start=date(2015, 1, 5),
        data_end=date(2026, 5, 18),
        ticker_count=3,
        signal_count=14,
        notes=None,
        strategy_kind="analysis_contract",
        similarity_threshold=12,
    )
    db_session.add(run)
    db_session.flush()
    for index in range(5):
        db_session.add(
            BacktestSignal(
                run_id=run.id,
                ticker="111111",
                name="Winner",
                signal_date=date(2024, 1, 1 + index),
                score=12,
                score_bucket="12",
                entry_date=date(2024, 1, 2 + index),
                entry_price=100,
                exit_reason="target",
                event_return=0.10,
                days_held=5,
            )
        )
        db_session.add(
            BacktestSignal(
                run_id=run.id,
                ticker="222222",
                name="Loser",
                signal_date=date(2024, 2, 1 + index),
                score=12,
                score_bucket="12",
                entry_date=date(2024, 2, 2 + index),
                entry_price=100,
                exit_reason="stop",
                event_return=-0.05,
                days_held=5,
            )
        )
    for index in range(4):
        db_session.add(
            BacktestSignal(
                run_id=run.id,
                ticker="333333",
                name="Small Sample",
                signal_date=date(2024, 3, 1 + index),
                score=12,
                score_bucket="12",
                entry_date=date(2024, 3, 2 + index),
                entry_price=100,
                exit_reason="target",
                event_return=0.50,
                days_held=5,
            )
        )
    db_session.commit()

    resp = client.get(f"/api/backtest/runs/{run.id}")

    assert resp.status_code == 200
    breakdown = resp.json()["contract_breakdown"]
    assert breakdown["top_tickers"][0]["ticker"] == "111111"
    assert breakdown["top_tickers"][0]["mean_return"] == pytest.approx(0.10)
    assert breakdown["bottom_tickers"][0]["ticker"] == "222222"
    assert [item["ticker"] for item in breakdown["top_tickers"]] == ["111111", "222222"]


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


def test_get_daily_rally_insights_returns_rules_for_run(
    client: TestClient,
    db_session: Session,
) -> None:
    run = BacktestRun(
        created_at=datetime(2026, 5, 24, 9, 0, 0),
        universe="KOSPI200-DB",
        buy_threshold=0,
        horizons="20d,40d,60d,120d",
        warmup_weeks=0,
        data_start=date(2024, 1, 1),
        data_end=date(2024, 2, 1),
        ticker_count=1,
        signal_count=1,
        strategy_kind="daily_20d_40pct_rally",
    )
    db_session.add(run)
    db_session.flush()
    db_session.add_all(
        [
            DailyRallyRuleStat(
                run_id=run.id,
                rule_key="low",
                rule_label="low",
                support=10,
                positives=10,
                total_matches=30,
                precision=0.3,
                base_rate=0.1,
                lift=3.0,
                score=2.0,
            ),
            DailyRallyRuleStat(
                run_id=run.id,
                rule_key="high",
                rule_label="high",
                support=5,
                positives=5,
                total_matches=10,
                precision=0.5,
                base_rate=0.1,
                lift=5.0,
                score=8.0,
            ),
        ]
    )
    db_session.commit()

    resp = client.get(f"/api/backtest/runs/{run.id}/daily-rally-insights", params={"limit": 1})

    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == run.id
    assert body["rule_count"] == 1
    assert [rule["rule_key"] for rule in body["rules"]] == ["high"]


def test_get_daily_rally_candidates_decodes_json(
    client: TestClient,
    db_session: Session,
) -> None:
    run = BacktestRun(
        created_at=datetime(2026, 5, 24, 9, 0, 0),
        universe="KOSPI200-DB",
        buy_threshold=0,
        horizons="20d,40d,60d,120d",
        warmup_weeks=0,
        data_start=date(2024, 1, 1),
        data_end=date(2024, 2, 1),
        ticker_count=1,
        signal_count=1,
        strategy_kind="daily_20d_40pct_rally",
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        DailyRallyCurrentCandidate(
            run_id=run.id,
            ticker="005930",
            name="Samsung",
            signal_date=date(2024, 2, 1),
            close_price=140.0,
            matched_rules_json='["ret_20d>=0.10"]',
            matched_rule_count=1,
            max_rule_score=1.5,
            mean_rule_score=1.5,
            features_json='{"ma5_gt_ma20": true, "ret_20d": 0.12}',
        )
    )
    db_session.commit()

    resp = client.get(f"/api/backtest/runs/{run.id}/daily-rally-candidates")

    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == run.id
    assert body["candidate_count"] == 1
    candidate = body["candidates"][0]
    assert candidate["matched_rules"] == ["ret_20d>=0.10"]
    assert candidate["features"] == {"ma5_gt_ma20": True, "ret_20d": 0.12}
    assert candidate["composite_score"] is None
    assert candidate["rule_breakdowns"] == []


def test_get_daily_rally_candidates_sorts_by_composite_with_nulls_last(
    client: TestClient,
    db_session: Session,
) -> None:
    run = BacktestRun(
        created_at=datetime(2026, 5, 24, 9, 0, 0),
        universe="KOSPI200-DB",
        buy_threshold=0,
        horizons="20d,40d,60d,120d",
        warmup_weeks=0,
        data_start=date(2024, 1, 1),
        data_end=date(2024, 2, 1),
        ticker_count=3,
        signal_count=3,
        strategy_kind="daily_20d_40pct_rally",
    )
    db_session.add(run)
    db_session.flush()

    def _candidate(ticker: str, composite_score: float | None, max_rule_score: float, **extra):
        return DailyRallyCurrentCandidate(
            run_id=run.id,
            ticker=ticker,
            name=ticker,
            signal_date=date(2024, 2, 1),
            close_price=100.0,
            matched_rules_json='["ret_20d>=0.10"]',
            matched_rule_count=1,
            max_rule_score=max_rule_score,
            mean_rule_score=max_rule_score,
            features_json="{}",
            composite_score=composite_score,
            **extra,
        )

    db_session.add_all(
        [
            _candidate("LEGACY", None, 99.0),
            _candidate("LOW", 30.0, 5.0),
            _candidate(
                "HIGH",
                80.0,
                1.0,
                best_rule_key="ret_20d>=0.10",
                rule_quality_score=1.0,
                stability_score=1.0,
                stability_classification="stable",
                expected_return_score=0.6,
                expected_win_rate_20d=0.7,
                expected_median_return_20d=0.2,
                score_breakdown_json=json.dumps(
                    [
                        {
                            "rule_key": "ret_20d>=0.10",
                            "rule_label": "ret_20d >= 0.10",
                            "rule_composite": 80.0,
                            "rule_quality": 1.0,
                            "stability_multiplier": 1.0,
                            "stability_classification": "stable",
                            "expected_return": 0.6,
                            "win_rate_20d": 0.7,
                            "median_return_20d": 0.2,
                        }
                    ]
                ),
            ),
        ]
    )
    db_session.commit()

    resp = client.get(f"/api/backtest/runs/{run.id}/daily-rally-candidates")

    assert resp.status_code == 200
    body = resp.json()
    assert [candidate["ticker"] for candidate in body["candidates"]] == ["HIGH", "LOW", "LEGACY"]
    top = body["candidates"][0]
    assert top["composite_score"] == pytest.approx(80.0)
    assert top["stability_classification"] == "stable"
    assert top["rule_breakdowns"][0]["rule_key"] == "ret_20d>=0.10"
    assert top["rule_breakdowns"][0]["stability_multiplier"] == pytest.approx(1.0)


def test_get_daily_rally_pattern_stats_decodes_return_stats(
    client: TestClient,
    db_session: Session,
) -> None:
    run = BacktestRun(
        created_at=datetime(2026, 5, 24, 9, 0, 0),
        universe="KOSPI200-DB",
        buy_threshold=0,
        horizons="20d,40d,60d,120d",
        warmup_weeks=0,
        data_start=date(2024, 1, 1),
        data_end=date(2024, 2, 1),
        ticker_count=1,
        signal_count=1,
        strategy_kind="daily_20d_40pct_rally",
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        DailyRallyPatternStat(
            run_id=run.id,
            pattern_key="ret_20d>=0.20",
            pattern_label="ret_20d >= 0.20",
            support=2,
            positives=2,
            total_matches=3,
            precision=2 / 3,
            base_rate=0.25,
            lift=(2 / 3) / 0.25,
            score=2.2,
            return_stats_json='{"20":{"horizon":20,"count":3,"censored_count":0,"win_rate":0.6666666667,"mean":0.2,"median":0.1,"std":0.3,"p25":0.0,"p75":0.35,"min":-0.1,"max":0.5}}',
        )
    )
    db_session.commit()

    resp = client.get(f"/api/backtest/runs/{run.id}/daily-rally-pattern-stats")

    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == run.id
    assert body["pattern_count"] == 1
    pattern = body["patterns"][0]
    assert pattern["pattern_key"] == "ret_20d>=0.20"
    assert pattern["return_stats"][0]["horizon"] == 20
    assert pattern["return_stats"][0]["mean"] == pytest.approx(0.2)


def test_get_daily_rally_pattern_stats_rejects_non_daily_rally_run(
    client: TestClient,
    db_session: Session,
) -> None:
    run_id = _seed(db_session)

    resp = client.get(f"/api/backtest/runs/{run_id}/daily-rally-pattern-stats")

    assert resp.status_code == 404


def test_get_daily_rally_validation_decodes_summary(
    client: TestClient,
    db_session: Session,
) -> None:
    run = BacktestRun(
        created_at=datetime(2026, 5, 24, 9, 0, 0),
        universe="KOSPI200-DB",
        buy_threshold=0,
        horizons="20d,40d,60d,120d",
        warmup_weeks=0,
        data_start=date(2024, 1, 1),
        data_end=date(2026, 6, 5),
        ticker_count=1,
        signal_count=2,
        strategy_kind="daily_20d_40pct_rally",
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        DailyRallyValidationSummary(
            run_id=run.id,
            summary_json=(
                '{"summary":{"sample_count":2,"complete_years":[2024],"partial_years":[2026],'
                '"top_positive_ticker_share":0.5,"walk_forward_median_lift":1.35},'
                '"year_breakdown":[{"year":2026,"total":2,"positives":1,"base_rate":0.5,'
                '"positive_forward_return_120d_mean":null,"censored_120d_count":2,"partial":true}],'
                '"ticker_concentration":[{"ticker":"005930","name":"Samsung","total_count":2,'
                '"positive_count":1,"positive_share":0.5}],'
                '"pattern_stability":[{"pattern_key":"ret_20d>=0.20","pattern_label":"ret_20d >= 0.20",'
                '"total_matches":10,"positives":3,"full_period_lift":1.4,"test_window_count":5,'
                '"median_train_lift":1.5,"median_test_lift":1.3,"test_lift_gt_1_ratio":0.8,'
                '"classification":"stable"}],'
                '"walk_forward_windows":[{"train_years":[2021,2022,2023],"test_year":2024,'
                '"pattern_key":"ret_20d>=0.20","pattern_label":"ret_20d >= 0.20","train_support":5,'
                '"train_total_matches":12,"train_precision":0.4167,"train_base_rate":0.2,"train_lift":2.0835,'
                '"test_matches":4,"test_positives":1,"test_precision":0.25,"test_base_rate":0.2,'
                '"test_lift":1.25,"classification":"stable"}],'
                '"warnings":["2026 has censored 120d returns and is excluded from stability checks."]}'
            ),
        )
    )
    db_session.commit()

    resp = client.get(f"/api/backtest/runs/{run.id}/daily-rally-validation")

    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == run.id
    assert body["summary"]["partial_years"] == [2026]
    assert body["year_breakdown"][0]["partial"] is True
    assert body["ticker_concentration"][0]["ticker"] == "005930"
    assert body["pattern_stability"][0]["classification"] == "stable"
    assert body["walk_forward_windows"][0]["test_lift"] == pytest.approx(1.25)
    assert "2026" in body["warnings"][0]


def test_get_daily_rally_validation_rejects_non_daily_rally_run(
    client: TestClient,
    db_session: Session,
) -> None:
    run_id = _seed(db_session)

    resp = client.get(f"/api/backtest/runs/{run_id}/daily-rally-validation")

    assert resp.status_code == 404


def test_get_daily_rally_insights_rejects_non_daily_rally_run(
    client: TestClient,
    db_session: Session,
) -> None:
    run_id = _seed(db_session)

    resp = client.get(f"/api/backtest/runs/{run_id}/daily-rally-insights")

    assert resp.status_code == 404


def test_run_detail_404(client: TestClient) -> None:
    resp = client.get("/api/backtest/runs/999999")
    assert resp.status_code == 404


def test_universe_api_lists_adds_deactivates_and_reactivates(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backtest, "run_backtest_preload_pipeline", lambda job_id: None)
    db_session.add(
        BacktestUniverseMember(
            ticker="000660",
            name="SK Hynix",
            market="KR",
            active=False,
            sort_order=2,
            source="test",
        )
    )
    db_session.commit()

    add_resp = client.post(
        "/api/backtest/universe",
        json={"ticker": "5930", "name": "Samsung", "sort_order": 1},
    )
    assert add_resp.status_code == 201
    assert add_resp.json()["ticker"] == "005930"
    assert add_resp.json()["active"] is True

    duplicate_resp = client.post(
        "/api/backtest/universe",
        json={"ticker": "005930", "name": "Samsung Electronics"},
    )
    assert duplicate_resp.status_code == 409

    list_resp = client.get("/api/backtest/universe", params={"include_inactive": "true"})
    assert list_resp.status_code == 200
    assert [item["ticker"] for item in list_resp.json()] == ["005930", "000660"]

    patch_resp = client.patch(
        "/api/backtest/universe/005930",
        json={"active": False, "name": "Samsung Electronics", "sort_order": 3},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["active"] is False
    assert patch_resp.json()["name"] == "Samsung Electronics"

    active_only_resp = client.get("/api/backtest/universe")
    assert active_only_resp.status_code == 200
    assert active_only_resp.json() == []

    reactivate_resp = client.patch("/api/backtest/universe/000660", json={"active": True})
    assert reactivate_resp.status_code == 200
    assert reactivate_resp.json()["active"] is True

    delete_resp = client.delete("/api/backtest/universe/000660")
    assert delete_resp.status_code == 204
    assert db_session.get(BacktestUniverseMember, "000660").active is False


def test_create_universe_member_creates_preload_job(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called_job_ids: list[int] = []
    monkeypatch.setattr(
        backtest,
        "run_backtest_preload_pipeline",
        lambda job_id: called_job_ids.append(job_id),
    )

    add_resp = client.post(
        "/api/backtest/universe",
        json={"ticker": "5930", "name": "Samsung", "sort_order": 1},
    )

    assert add_resp.status_code == 201
    job = db_session.scalar(
        backtest.select(BacktestPreloadJob).where(BacktestPreloadJob.ticker == "005930")
    )
    assert job is not None
    assert job.name == "Samsung"
    assert job.status == "pending"
    assert called_job_ids == [job.id]


def test_reactivating_universe_member_creates_preload_job(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called_job_ids: list[int] = []
    monkeypatch.setattr(
        backtest,
        "run_backtest_preload_pipeline",
        lambda job_id: called_job_ids.append(job_id),
    )
    db_session.add(
        BacktestUniverseMember(
            ticker="000660",
            name="SK Hynix",
            market="KR",
            active=False,
            sort_order=2,
            source="test",
        )
    )
    db_session.commit()

    resp = client.patch("/api/backtest/universe/000660", json={"active": True})

    assert resp.status_code == 200
    job = db_session.scalar(
        backtest.select(BacktestPreloadJob).where(BacktestPreloadJob.ticker == "000660")
    )
    assert job is not None
    assert job.name == "SK Hynix"
    assert job.status == "pending"
    assert called_job_ids == [job.id]


def test_reactivating_universe_member_skips_duplicate_active_preload_job(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called_job_ids: list[int] = []
    monkeypatch.setattr(
        backtest,
        "run_backtest_preload_pipeline",
        lambda job_id: called_job_ids.append(job_id),
    )
    db_session.add(
        BacktestUniverseMember(
            ticker="000660",
            name="SK Hynix",
            market="KR",
            active=False,
            sort_order=2,
            source="test",
        )
    )
    existing_job = BacktestPreloadJob(ticker="000660", name="SK Hynix", status="running")
    db_session.add(existing_job)
    db_session.commit()
    existing_job_id = existing_job.id

    resp = client.patch("/api/backtest/universe/000660", json={"active": True})

    assert resp.status_code == 200
    jobs = list(
        db_session.scalars(
            backtest.select(BacktestPreloadJob).where(BacktestPreloadJob.ticker == "000660")
        ).all()
    )
    assert [job.id for job in jobs] == [existing_job_id]
    assert called_job_ids == []


def test_run_backtest_preload_pipeline_marks_done(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = BacktestPreloadJob(ticker="005930", name="Samsung")
    db_session.add(job)
    db_session.commit()
    job_id = job.id

    monkeypatch.setattr(backtest, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(
        backtest,
        "preload_daily_bars",
        lambda db, universe: PreloadDailyResult(processed=1, skipped=0, upserted_rows=7),
    )

    backtest.run_backtest_preload_pipeline(job_id)

    saved = db_session.get(BacktestPreloadJob, job_id)
    assert saved is not None
    assert saved.status == "done"
    assert saved.processed == 1
    assert saved.skipped == 0
    assert saved.upserted_rows == 7
    assert saved.error_message is None
    assert saved.completed_at is not None


def test_run_backtest_preload_pipeline_marks_failed_on_empty_response(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = BacktestPreloadJob(ticker="005930", name="Samsung")
    db_session.add(job)
    db_session.commit()
    job_id = job.id

    monkeypatch.setattr(backtest, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(
        backtest,
        "preload_daily_bars",
        lambda db, universe: PreloadDailyResult(
            processed=0,
            skipped=0,
            upserted_rows=0,
            failed=[("005930", "Samsung", "no daily data returned")],
        ),
    )

    backtest.run_backtest_preload_pipeline(job_id)

    saved = db_session.get(BacktestPreloadJob, job_id)
    assert saved is not None
    assert saved.status == "failed"
    assert saved.processed == 0
    assert saved.upserted_rows == 0
    assert saved.error_message == "005930 Samsung: no daily data returned"
    assert saved.completed_at is not None


def test_universe_api_rejects_non_kr_ticker(client: TestClient) -> None:
    resp = client.post("/api/backtest/universe", json={"ticker": "AAPL", "name": "Apple"})

    assert resp.status_code == 400


def test_universe_api_accepts_alphanumeric_krx_ticker(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backtest, "run_backtest_preload_pipeline", lambda job_id: None)

    resp = client.post(
        "/api/backtest/universe",
        json={"ticker": "a12345", "name": "Alpha KRX"},
    )

    assert resp.status_code == 201
    assert resp.json()["ticker"] == "A12345"
    assert db_session.get(BacktestUniverseMember, "A12345") is not None
