from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.database import Base
from backend.models import Analysis, AnalysisJob, KrxStock, Run, StockPrice, UsStock
from scripts.migrate_sqlite_to_mariadb import migrate


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _session_factory(path: Path) -> sessionmaker[Session]:
    engine = create_engine(_sqlite_url(path), connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def test_migrate_preserves_rows_and_foreign_keys(tmp_path: Path) -> None:
    source_path = tmp_path / "source.db"
    target_path = tmp_path / "target.db"
    SourceSession = _session_factory(source_path)
    created_at = datetime(2026, 5, 7, 9, 30, 0)

    with SourceSession() as db:
        db.add(Run(id=1, memo="seed", created_at=created_at))
        db.add(
            Analysis(
                id=10,
                run_id=1,
                ticker="005930",
                name="Samsung Electronics",
                name_initials="SE",
                model="gpt-5.4",
                markdown="analysis",
                judgment="BUY",
                trend="UP",
                cloud_position="ABOVE",
                ma_alignment="BULLISH",
                entry_price=100.0,
                entry_price_max=110.0,
                target_price=130.0,
                target_price_max=140.0,
                stop_loss=90.0,
                stop_loss_max=95.0,
                created_at=created_at,
            )
        )
        db.add(
            AnalysisJob(
                id=20,
                ticker="005930",
                run_id=1,
                model="codex",
                status="done",
                error_message=None,
                raw_markdown="analysis",
                analysis_id=10,
                created_at=created_at,
            )
        )
        db.add(
            StockPrice(
                ticker="005930",
                price_date=date(2026, 5, 7),
                close_price=123.0,
                fetched_at=created_at,
            )
        )
        db.add(KrxStock(code="005930", name="Samsung", name_initials="S", updated_at=created_at))
        db.add(UsStock(code="AAPL", name="Apple Inc", market="NASDAQ", updated_at=created_at))
        db.commit()

    counts = migrate(source_path, _sqlite_url(target_path), create_schema=False, dry_run=False)

    assert counts == {
        "runs": 1,
        "analyses": 1,
        "analysis_jobs": 1,
        "stock_prices": 1,
        "krx_stocks": 1,
        "us_stocks": 1,
    }

    TargetSession = _session_factory(target_path)
    with TargetSession() as db:
        analysis = db.scalars(select(Analysis)).one()
        job = db.scalars(select(AnalysisJob)).one()
        assert analysis.id == 10
        assert analysis.run_id == 1
        assert job.analysis_id == 10


def test_migrate_dry_run_rolls_back_inserted_rows(tmp_path: Path) -> None:
    source_path = tmp_path / "source.db"
    target_path = tmp_path / "target.db"
    SourceSession = _session_factory(source_path)
    with SourceSession() as db:
        db.add(Run(id=1, memo=None, created_at=datetime(2026, 5, 7, 9, 30, 0)))
        db.commit()

    counts = migrate(source_path, _sqlite_url(target_path), create_schema=False, dry_run=True)

    assert counts["runs"] == 1
    TargetSession = _session_factory(target_path)
    with TargetSession() as db:
        assert db.query(Run).count() == 0
