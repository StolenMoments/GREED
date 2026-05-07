from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from backend.database import Base
from backend.models import Analysis, Run
from scripts.import_sqlite_analyses_to_mariadb import import_analyses


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _session_factory(path: Path) -> sessionmaker[Session]:
    engine = create_engine(_sqlite_url(path), connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _seed_source(path: Path) -> None:
    SessionLocal = _session_factory(path)
    created_at = datetime(2026, 5, 7, 9, 30, 0)
    with SessionLocal() as db:
        db.add(Run(id=1, memo="source run", created_at=created_at))
        db.add_all(
            [
                Analysis(
                    id=10,
                    run_id=1,
                    ticker="005930",
                    name="Samsung Electronics",
                    name_initials="SE",
                    model="codex",
                    markdown="analysis 1",
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
                ),
                Analysis(
                    id=11,
                    run_id=1,
                    ticker="AAPL",
                    name="Apple Inc",
                    name_initials="AI",
                    model="gemini",
                    markdown="analysis 2",
                    judgment="HOLD",
                    trend="SIDEWAYS",
                    cloud_position="INSIDE",
                    ma_alignment="MIXED",
                    entry_price=None,
                    entry_price_max=None,
                    target_price=None,
                    target_price_max=None,
                    stop_loss=None,
                    stop_loss_max=None,
                    created_at=created_at,
                ),
            ]
        )
        db.commit()


def test_import_analyses_attaches_rows_to_max_target_run_id(tmp_path: Path) -> None:
    source_path = tmp_path / "source.db"
    target_path = tmp_path / "target.db"
    _seed_source(source_path)
    TargetSession = _session_factory(target_path)
    with TargetSession() as db:
        db.add_all(
            [
                Run(id=3, memo="older", created_at=datetime(2026, 5, 1, 9, 0, 0)),
                Run(id=7, memo="latest", created_at=datetime(2026, 5, 2, 9, 0, 0)),
            ]
        )
        db.commit()

    result = import_analyses(source_path, _sqlite_url(target_path), dry_run=False)

    assert result == {
        "target_run_id": 7,
        "source_analyses": 2,
        "inserted_analyses": 2,
        "dry_run": False,
    }
    with TargetSession() as db:
        rows = db.scalars(select(Analysis).order_by(Analysis.id)).all()
        assert [row.run_id for row in rows] == [7, 7]
        assert [row.ticker for row in rows] == ["005930", "AAPL"]
        assert {row.id for row in rows}.isdisjoint({10, 11})


def test_import_analyses_dry_run_rolls_back(tmp_path: Path) -> None:
    source_path = tmp_path / "source.db"
    target_path = tmp_path / "target.db"
    _seed_source(source_path)
    TargetSession = _session_factory(target_path)
    with TargetSession() as db:
        db.add(Run(id=1, memo="target", created_at=datetime(2026, 5, 1, 9, 0, 0)))
        db.commit()

    result = import_analyses(source_path, _sqlite_url(target_path), dry_run=True)

    assert result["inserted_analyses"] == 2
    assert result["dry_run"] is True
    with TargetSession() as db:
        assert db.query(Analysis).count() == 0


def test_import_analyses_requires_target_run(tmp_path: Path) -> None:
    source_path = tmp_path / "source.db"
    target_path = tmp_path / "target.db"
    _seed_source(source_path)
    _session_factory(target_path)

    with pytest.raises(RuntimeError, match="Target DB has no runs"):
        import_analyses(source_path, _sqlite_url(target_path), dry_run=False)


def test_import_analyses_requires_current_source_schema(tmp_path: Path) -> None:
    source_path = tmp_path / "source.db"
    target_path = tmp_path / "target.db"
    source_engine = create_engine(_sqlite_url(source_path), connect_args={"check_same_thread": False})
    with source_engine.begin() as conn:
        conn.execute(text("CREATE TABLE analyses (id INTEGER PRIMARY KEY, ticker TEXT NOT NULL)"))
    TargetSession = _session_factory(target_path)
    with TargetSession() as db:
        db.add(Run(id=1, memo="target", created_at=datetime(2026, 5, 1, 9, 0, 0)))
        db.commit()

    with pytest.raises(RuntimeError, match="missing required columns"):
        import_analyses(source_path, _sqlite_url(target_path), dry_run=False)
