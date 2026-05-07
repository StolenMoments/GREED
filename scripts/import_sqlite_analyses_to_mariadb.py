"""Import only analysis rows from a source SQLite greed.db into MariaDB.

This is for appending analysis history from another PC after the main database
has already been migrated to MariaDB. It does not import runs, jobs, prices, or
ticker master data. Every imported analysis is attached to the current maximum
run id in the target database.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.database import build_engine_kwargs
from backend.models import Analysis, Run


ANALYSIS_COLUMNS = {
    "id",
    "run_id",
    "ticker",
    "name",
    "name_initials",
    "model",
    "markdown",
    "judgment",
    "trend",
    "cloud_position",
    "ma_alignment",
    "entry_price",
    "entry_price_max",
    "target_price",
    "target_price_max",
    "stop_loss",
    "stop_loss_max",
    "created_at",
}
TARGET_TABLES = {"runs", "analyses"}


def _sqlite_engine(db_path: Path) -> Engine:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {db_path}")
    return create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )


def _target_engine(database_url: str) -> Engine:
    return create_engine(database_url, **build_engine_kwargs(database_url))


def _session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _assert_source_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if "analyses" not in set(inspector.get_table_names()):
        raise RuntimeError("Source DB does not contain an analyses table")

    columns = {column["name"] for column in inspector.get_columns("analyses")}
    missing = sorted(ANALYSIS_COLUMNS - columns)
    if missing:
        raise RuntimeError(
            "Source analyses table is missing required columns: " + ", ".join(missing)
        )


def _assert_target_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    missing = sorted(TARGET_TABLES - set(inspector.get_table_names()))
    if missing:
        raise RuntimeError("Target DB is missing required tables: " + ", ".join(missing))


def _copy_analysis(row: Analysis, target_run_id: int) -> Analysis:
    return Analysis(
        run_id=target_run_id,
        ticker=row.ticker,
        name=row.name,
        name_initials=row.name_initials,
        model=row.model,
        markdown=row.markdown,
        judgment=row.judgment,
        trend=row.trend,
        cloud_position=row.cloud_position,
        ma_alignment=row.ma_alignment,
        entry_price=row.entry_price,
        entry_price_max=row.entry_price_max,
        target_price=row.target_price,
        target_price_max=row.target_price_max,
        stop_loss=row.stop_loss,
        stop_loss_max=row.stop_loss_max,
        created_at=row.created_at,
    )


def import_analyses(source_path: Path, target_url: str, *, dry_run: bool) -> dict[str, int | bool]:
    source_engine = _sqlite_engine(source_path)
    target_engine = _target_engine(target_url)
    try:
        _assert_source_schema(source_engine)
        _assert_target_schema(target_engine)

        SourceSession = _session_factory(source_engine)
        TargetSession = _session_factory(target_engine)
        with SourceSession() as src, TargetSession() as dst:
            target_run_id = dst.scalar(select(func.max(Run.id)))
            if target_run_id is None:
                raise RuntimeError("Target DB has no runs. Create at least one run first.")

            source_rows = src.scalars(select(Analysis).order_by(Analysis.id)).all()
            for row in source_rows:
                dst.add(_copy_analysis(row, target_run_id))

            inserted = len(source_rows)
            dst.flush()
            if dry_run:
                dst.rollback()
            else:
                dst.commit()

            return {
                "target_run_id": target_run_id,
                "source_analyses": inserted,
                "inserted_analyses": inserted,
                "dry_run": dry_run,
            }
    finally:
        source_engine.dispose()
        target_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Source SQLite greed.db path")
    parser.add_argument("--target", default=os.getenv("DATABASE_URL"), help="Target MariaDB URL")
    parser.add_argument("--dry-run", action="store_true", help="Rollback after checking import counts")
    args = parser.parse_args()

    if not args.target:
        parser.error("--target or DATABASE_URL is required")

    result = import_analyses(args.source, args.target, dry_run=args.dry_run)
    action = "DRY-RUN" if args.dry_run else "COMMIT"
    print(f"[{action}] analysis import completed")
    print(f"  - target_run_id: {result['target_run_id']}")
    print(f"  - source_analyses: {result['source_analyses']}")
    print(f"  - inserted_analyses: {result['inserted_analyses']}")


if __name__ == "__main__":
    main()
