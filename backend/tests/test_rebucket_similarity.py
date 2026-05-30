from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.models import BacktestRun, BacktestSignal, BacktestStat
from scripts.backtest.rebucket_similarity import rebucket_similarity_run


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _seed_similarity_run(db: Session) -> int:
    run = BacktestRun(
        created_at=datetime(2026, 5, 30, 9, 0, 0),
        universe="KOSPI200",
        buy_threshold=10,
        horizons="4,8,12,26",
        warmup_weeks=120,
        data_start=date(2020, 1, 1),
        data_end=date(2021, 1, 1),
        ticker_count=2,
        signal_count=3,
        notes=None,
        source_analysis_id=1,
        strategy_kind="analysis_similarity",
        similarity_threshold=10,
    )
    db.add(run)
    db.flush()
    db.add(
        BacktestStat(
            run_id=run.id,
            horizon=26,
            score_bucket="12+",
            count=3,
            censored_count=0,
            win_rate=0.5,
            mean=0.0,
            median=0.0,
            std=0.0,
            p25=0.0,
            p75=0.0,
            min=0.0,
            max=0.0,
        )
    )
    for idx, (score, bucket, ret_26w) in enumerate(
        [(13, "12+", 0.2), (13, "12+", -0.1), (14, "12+", 0.4)],
        start=1,
    ):
        db.add(
            BacktestSignal(
                run_id=run.id,
                ticker=f"00000{idx}",
                name=f"Stock {idx}",
                signal_date=date(2020, idx, 1),
                score=score,
                score_bucket=bucket,
                entry_date=date(2020, idx, 8),
                entry_price=100.0,
                ret_4w=ret_26w / 4,
                ret_8w=ret_26w / 3,
                ret_12w=ret_26w / 2,
                ret_26w=ret_26w,
            )
        )
    db.commit()
    return run.id


def test_rebucket_similarity_run_replaces_legacy_buckets_with_exact_scores(
    db_session: Session,
) -> None:
    run_id = _seed_similarity_run(db_session)

    result = rebucket_similarity_run(db_session, run_id=run_id, dry_run=False)

    assert result.updated_signals == 3
    signals = db_session.scalars(
        select(BacktestSignal).where(BacktestSignal.run_id == run_id).order_by(BacktestSignal.id)
    ).all()
    assert [signal.score_bucket for signal in signals] == ["13", "13", "14"]

    stats = db_session.scalars(
        select(BacktestStat)
        .where(BacktestStat.run_id == run_id, BacktestStat.horizon == 26)
        .order_by(BacktestStat.score_bucket)
    ).all()
    by_bucket = {stat.score_bucket: stat for stat in stats}
    assert set(by_bucket) == {"10", "11", "12", "13", "14", "ALL"}
    assert by_bucket["13"].count == 2
    assert by_bucket["13"].win_rate == pytest.approx(0.5)
    assert by_bucket["14"].count == 1
    assert by_bucket["14"].win_rate == pytest.approx(1.0)
    assert by_bucket["ALL"].count == 3
    assert by_bucket["ALL"].win_rate == pytest.approx(2 / 3)
