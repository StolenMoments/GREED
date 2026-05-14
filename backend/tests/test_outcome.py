from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.models import Analysis, Run
from backend.outcome import (
    OUTCOME_NA,
    OUTCOME_ONGOING,
    OUTCOME_STOP,
    OUTCOME_TARGET,
    evaluate_outcome,
    evaluate_single_outcome,
    run_evaluate_outcomes,
)


def make_analysis(
    *,
    created_at: datetime,
    target_price: float | None = 175000,
    stop_loss: float | None = 125000,
    outcome: str | None = None,
) -> Analysis:
    return Analysis(
        run_id=1,
        ticker="011790",
        name="SKC",
        model="gemini-cli",
        markdown="analysis",
        judgment="매수",
        trend="상승",
        cloud_position="구름 위",
        ma_alignment="정배열",
        target_price=target_price,
        stop_loss=stop_loss,
        outcome=outcome,
        created_at=created_at,
    )


def make_daily_df(rows: list[tuple[str, int, int]]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"High": high, "Low": low} for _, high, low in rows],
        index=pd.to_datetime([day for day, _, _ in rows]),
    )


def test_evaluate_outcome_ignores_prices_before_and_on_analysis_date() -> None:
    analysis = make_analysis(created_at=datetime(2026, 5, 13, 12, 23, 3))
    df = make_daily_df(
        [
            ("2026-05-11", 179500, 155700),
            ("2026-05-13", 180000, 136700),
            ("2026-05-14", 148900, 137600),
        ]
    )

    outcome, outcome_date, outcome_price = evaluate_outcome(analysis, df)

    assert outcome == OUTCOME_ONGOING
    assert outcome_date is None
    assert outcome_price is None


def test_evaluate_outcome_uses_first_trade_date_after_analysis_date() -> None:
    analysis = make_analysis(created_at=datetime(2026, 5, 13, 12, 23, 3))
    df = make_daily_df(
        [
            ("2026-05-13", 180000, 136700),
            ("2026-05-14", 148900, 137600),
            ("2026-05-15", 175500, 140000),
        ]
    )

    outcome, outcome_date, outcome_price = evaluate_outcome(analysis, df)

    assert outcome == OUTCOME_TARGET
    assert outcome_date == pd.Timestamp("2026-05-15").date()
    assert outcome_price == 175500


def test_evaluate_outcome_keeps_stop_priority_when_both_hit_same_day() -> None:
    analysis = make_analysis(created_at=datetime(2026, 5, 13, 12, 23, 3))
    df = make_daily_df([("2026-05-14", 180000, 124000)])

    outcome, outcome_date, outcome_price = evaluate_outcome(analysis, df)

    assert outcome == OUTCOME_STOP
    assert outcome_date == pd.Timestamp("2026-05-14").date()
    assert outcome_price == 124000


def test_run_evaluate_outcomes_force_recalculates_existing_outcomes(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        run = Run(memo="outcome force test")
        session.add(run)
        session.flush()

        analysis = make_analysis(
            created_at=datetime(2026, 5, 13, 12, 23, 3),
            outcome=OUTCOME_TARGET,
        )
        analysis.run_id = run.id
        session.add(analysis)
        session.commit()

        monkeypatch.setattr(
            "backend.outcome.fetch_daily_df",
            lambda ticker, start, db=None: make_daily_df([("2026-05-14", 148900, 137600)]),
        )

        result = run_evaluate_outcomes(session)
        session.refresh(analysis)
        assert result == {"evaluated": 0, "skipped": 0}
        assert analysis.outcome == OUTCOME_TARGET

        result = run_evaluate_outcomes(session, force=True)
        session.refresh(analysis)
        assert result == {"evaluated": 1, "skipped": 0}
        assert analysis.outcome == OUTCOME_ONGOING
        assert analysis.outcome_date is None
        assert analysis.outcome_price is None
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_run_evaluate_outcomes_recalculates_ongoing_but_skips_terminal(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        run = Run(memo="outcome ongoing test")
        session.add(run)
        session.flush()

        ongoing = make_analysis(
            created_at=datetime(2026, 5, 13, 12, 23, 3),
            outcome=OUTCOME_ONGOING,
        )
        ongoing.run_id = run.id
        terminal = make_analysis(
            created_at=datetime(2026, 5, 13, 12, 23, 3),
            outcome=OUTCOME_NA,
        )
        terminal.run_id = run.id
        session.add_all([ongoing, terminal])
        session.commit()

        monkeypatch.setattr(
            "backend.outcome.fetch_daily_df",
            lambda ticker, start, db=None: make_daily_df([("2026-05-14", 175500, 140000)]),
        )

        result = run_evaluate_outcomes(session)
        session.refresh(ongoing)
        session.refresh(terminal)

        assert result == {"evaluated": 1, "skipped": 0}
        assert ongoing.outcome == OUTCOME_TARGET
        assert terminal.outcome == OUTCOME_NA
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_evaluate_single_outcome_uses_price_bar_cache_layer(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        run = Run(memo="single outcome cache test")
        session.add(run)
        session.flush()
        analysis = make_analysis(created_at=datetime(2026, 5, 13, 12, 23, 3))
        analysis.run_id = run.id
        session.add(analysis)
        session.commit()

        calls: list[tuple[str, datetime.date]] = []

        def fake_fetch_price_bars_df(db, ticker, start):
            calls.append((ticker, start))
            return make_daily_df([("2026-05-14", 175500, 140000)])

        monkeypatch.setattr("backend.outcome.fetch_price_bars_df", fake_fetch_price_bars_df)

        assert evaluate_single_outcome(session, analysis) is True
        session.refresh(analysis)
        assert calls == [("011790", datetime(2026, 5, 13).date())]
        assert analysis.outcome == OUTCOME_TARGET
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_run_evaluate_outcomes_fetches_once_per_ticker(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        run = Run(memo="batch outcome cache test")
        session.add(run)
        session.flush()
        older = make_analysis(created_at=datetime(2026, 5, 12, 12, 23, 3))
        newer = make_analysis(created_at=datetime(2026, 5, 13, 12, 23, 3))
        older.run_id = run.id
        newer.run_id = run.id
        session.add_all([older, newer])
        session.commit()

        calls: list[tuple[str, datetime.date]] = []

        def fake_fetch_price_bars_df(db, ticker, start):
            calls.append((ticker, start))
            return make_daily_df([("2026-05-14", 175500, 140000)])

        monkeypatch.setattr("backend.outcome.fetch_price_bars_df", fake_fetch_price_bars_df)

        result = run_evaluate_outcomes(session)

        assert result == {"evaluated": 2, "skipped": 0}
        assert calls == [("011790", datetime(2026, 5, 12).date())]
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_run_evaluate_outcomes_skips_when_cache_fetch_returns_none(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        run = Run(memo="batch outcome fetch failure test")
        session.add(run)
        session.flush()
        analysis = make_analysis(created_at=datetime(2026, 5, 13, 12, 23, 3))
        analysis.run_id = run.id
        session.add(analysis)
        session.commit()

        monkeypatch.setattr(
            "backend.outcome.fetch_price_bars_df",
            lambda db, ticker, start: None,
        )

        result = run_evaluate_outcomes(session)

        assert result == {"evaluated": 0, "skipped": 1}
        session.refresh(analysis)
        assert analysis.outcome is None
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
