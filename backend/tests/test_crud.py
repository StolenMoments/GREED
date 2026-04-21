from __future__ import annotations

from collections.abc import Generator
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.crud import (
    create_analysis,
    create_run,
    get_analyses_by_run,
    get_analysis,
    get_analysis_history,
    get_run,
    get_runs,
    upsert_stock_price,
)
from backend.database import Base
from backend.schemas import AnalysisCreate
from backend.timezone import seoul_now


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_create_run_persists_run(db_session: Session) -> None:
    run = create_run(db_session, memo="first run")

    assert run.id is not None
    assert run.memo == "first run"
    assert run.analysis_count == 0
    assert get_run(db_session, run.id) is not None


def test_create_run_uses_seoul_time(db_session: Session) -> None:
    run = create_run(db_session, memo="seoul time")

    now_in_seoul = seoul_now().replace(tzinfo=None)
    assert abs(now_in_seoul - run.created_at.replace(tzinfo=None)) < timedelta(seconds=5)


def test_get_runs_includes_analysis_count(db_session: Session) -> None:
    first_run = create_run(db_session, memo="first")
    second_run = create_run(db_session, memo="second")

    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=first_run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="gpt",
            markdown="analysis one",
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
            entry_price=70000,
            target_price=76000,
            stop_loss=66000,
        ),
    )
    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=first_run.id,
            ticker="000660",
            name="SK Hynix",
            model="gpt",
            markdown="analysis two",
            judgment="보유",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )

    runs = get_runs(db_session)

    assert [run.id for run in runs] == [second_run.id, first_run.id]
    run_counts = {run.id: run.analysis_count for run in runs}
    assert run_counts[first_run.id] == 2
    assert run_counts[second_run.id] == 0


def test_get_analyses_by_run_filters_by_judgment(db_session: Session) -> None:
    run = create_run(db_session, memo="filter target")

    buy_analysis = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="claude",
            markdown="buy markdown",
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )
    hold_analysis = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=run.id,
            ticker="000660",
            name="SK Hynix",
            model="claude",
            markdown="hold markdown",
            judgment="보유",
            trend="횡보",
            cloud_position="구름 속",
            ma_alignment="혼조",
        ),
    )

    all_analyses = get_analyses_by_run(db_session, run.id)
    buy_analyses = get_analyses_by_run(db_session, run.id, judgment="매수")

    assert [analysis.id for analysis in all_analyses] == [hold_analysis.id, buy_analysis.id]
    assert [analysis.id for analysis in buy_analyses] == [buy_analysis.id]


def test_get_analysis_history_orders_by_newest_first(db_session: Session) -> None:
    first_run = create_run(db_session, memo="history 1")
    second_run = create_run(db_session, memo="history 2")

    older = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=first_run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="gemini",
            markdown="older",
            judgment="보유",
            trend="횡보",
            cloud_position="구름 속",
            ma_alignment="혼조",
        ),
    )
    newer = create_analysis(
        db_session,
        AnalysisCreate(
            run_id=second_run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="gemini",
            markdown="newer",
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )
    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=second_run.id,
            ticker="000660",
            name="SK Hynix",
            model="gemini",
            markdown="other ticker",
            judgment="보유",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )

    history = get_analysis_history(db_session, "005930")

    assert [analysis.id for analysis in history] == [newer.id, older.id]
    assert get_analysis(db_session, newer.id).ticker == "005930"


def test_upsert_stock_price_uses_seoul_time(db_session: Session) -> None:
    stock_price = upsert_stock_price(
        db_session,
        ticker="005930",
        price_date=date(2026, 4, 21),
        close_price=70000,
    )

    now_in_seoul = seoul_now().replace(tzinfo=None)
    assert abs(now_in_seoul - stock_price.fetched_at.replace(tzinfo=None)) < timedelta(seconds=5)
