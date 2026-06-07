from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.database import Base
from backend.models import (
    BacktestRun,
    BacktestSignal,
    BacktestStat,
    DailyRallyCurrentCandidate,
    DailyRallyPatternStat,
    DailyRallyRuleStat,
)
from scripts.backtest.daily_rally import (
    DailyRallyBacktestResult,
    DailyRallyCandidate,
    DailyRallyPatternStat as EngineDailyRallyPatternStat,
    DailyRallyRule,
    DailyRallySample,
    DailyRallyReturnStat,
)
from scripts.backtest.persistence import persist_daily_rally_run


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_daily_rally_tables_are_created() -> None:
    assert "daily_rally_rule_stats" in Base.metadata.tables
    assert "daily_rally_pattern_stats" in Base.metadata.tables
    assert "daily_rally_current_candidates" in Base.metadata.tables
    assert DailyRallyRuleStat.__table__.name == "daily_rally_rule_stats"
    assert DailyRallyPatternStat.__table__.name == "daily_rally_pattern_stats"
    assert DailyRallyCurrentCandidate.__table__.name == "daily_rally_current_candidates"


def test_persist_daily_rally_run_writes_run_rules_and_candidates(db_session: Session) -> None:
    result = DailyRallyBacktestResult(
        samples=[
            DailyRallySample(
                ticker="005930",
                name="Samsung",
                signal_date=date(2024, 1, 2),
                close_price=100.0,
                label=1,
                forward_returns={20: 0.4, 40: 0.5, 60: None, 120: 0.8},
            ),
            DailyRallySample(
                ticker="000660",
                name="SK Hynix",
                signal_date=date(2024, 1, 3),
                close_price=50.0,
                label=0,
                forward_returns={20: -0.1, 40: 0.1, 60: 0.2, 120: None},
            ),
        ],
        rules=[
            DailyRallyRule(
                rule_key="ret_20d>=0.10",
                rule_label="ret_20d >= 0.10",
                support=1,
                positives=1,
                total_matches=2,
                precision=0.5,
                base_rate=0.25,
                lift=2.0,
                score=1.5,
            )
        ],
        current_candidates=[
            DailyRallyCandidate(
                ticker="005930",
                name="Samsung",
                signal_date=date(2024, 2, 1),
                close_price=140.0,
                matched_rules=["ret_20d>=0.10"],
                matched_rule_count=1,
                max_rule_score=1.5,
                mean_rule_score=1.5,
                features={"ret_20d": 0.12, "ma5_gt_ma20": True, "weekly_cloud_position": "above_cloud"},
            )
        ],
        pattern_stats=[
            EngineDailyRallyPatternStat(
                pattern_key="ret_20d>=0.10",
                pattern_label="ret_20d >= 0.10",
                support=1,
                positives=1,
                total_matches=2,
                precision=0.5,
                base_rate=0.25,
                lift=2.0,
                score=1.5,
                return_stats={
                    20: DailyRallyReturnStat(
                        horizon=20,
                        count=2,
                        censored_count=0,
                        win_rate=0.5,
                        mean=0.15,
                        median=0.15,
                        std=0.25,
                        p25=0.025,
                        p75=0.275,
                        min=-0.1,
                        max=0.4,
                    )
                },
            )
        ],
        ticker_count=2,
        data_start=date(2024, 1, 1),
        data_end=date(2024, 2, 1),
    )

    run_id = persist_daily_rally_run(db_session, result)

    run = db_session.get(BacktestRun, run_id)
    assert run is not None
    assert run.strategy_kind == "daily_20d_40pct_rally"
    assert run.horizons == "20d,40d,60d,120d"
    assert run.signal_count == 2

    signals = list(
        db_session.scalars(select(BacktestSignal).where(BacktestSignal.run_id == run_id)).all()
    )
    assert len(signals) == 2
    positive = next(signal for signal in signals if signal.ticker == "005930")
    assert positive.score == 1
    assert positive.score_bucket == "positive"
    assert positive.entry_date == positive.signal_date
    assert positive.ret_4w == pytest.approx(0.4)
    assert positive.ret_8w == pytest.approx(0.5)
    assert positive.ret_12w is None
    assert positive.ret_26w == pytest.approx(0.8)

    stats = list(db_session.scalars(select(BacktestStat).where(BacktestStat.run_id == run_id)).all())
    assert {(stat.horizon, stat.score_bucket) for stat in stats} == {
        (horizon, bucket)
        for horizon in (20, 40, 60, 120)
        for bucket in ("positive", "control", "ALL")
    }

    rule = db_session.scalar(select(DailyRallyRuleStat).where(DailyRallyRuleStat.run_id == run_id))
    assert rule is not None
    assert rule.rule_key == "ret_20d>=0.10"
    assert rule.score == pytest.approx(1.5)

    pattern = db_session.scalar(
        select(DailyRallyPatternStat).where(DailyRallyPatternStat.run_id == run_id)
    )
    assert pattern is not None
    assert pattern.pattern_key == "ret_20d>=0.10"
    assert pattern.score == pytest.approx(1.5)
    return_stats = json.loads(pattern.return_stats_json)
    assert return_stats["20"]["mean"] == pytest.approx(0.15)
    assert return_stats["20"]["count"] == 2

    candidate = db_session.scalar(
        select(DailyRallyCurrentCandidate).where(DailyRallyCurrentCandidate.run_id == run_id)
    )
    assert candidate is not None
    assert candidate.ticker == "005930"
    assert json.loads(candidate.matched_rules_json) == ["ret_20d>=0.10"]
    assert json.loads(candidate.features_json) == {
        "ma5_gt_ma20": True,
        "ret_20d": 0.12,
        "weekly_cloud_position": "above_cloud",
    }
