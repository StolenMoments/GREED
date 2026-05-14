"""Sync analyses added to SQLite after a given date into MariaDB, skipping rows already present.

Uses analysis.id as the deduplication key (assumes the initial migration preserved PKs via
migrate_sqlite_to_mariadb.py). If MariaDB IDs do not match SQLite IDs, the dry-run count
will look unexpectedly large — abort and investigate before committing.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.database import build_engine_kwargs
from backend.models import Analysis, Run


DEFAULT_SINCE = date(2025, 5, 4)


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


def _since_datetime(since: date) -> datetime:
    return datetime(since.year, since.month, since.day, tzinfo=timezone.utc)


def sync(
    source_path: Path,
    target_url: str,
    *,
    since: date,
    dry_run: bool,
) -> dict[str, int]:
    source_engine = _sqlite_engine(source_path)
    target_engine = _target_engine(target_url)
    try:
        since_dt = _since_datetime(since)

        SourceSession = _session_factory(source_engine)
        TargetSession = _session_factory(target_engine)

        with SourceSession() as src, TargetSession() as dst:
            # 1. SQLite: analyses since the cutoff date
            src_analyses: list[Analysis] = src.scalars(
                select(Analysis)
                .where(Analysis.created_at >= since_dt)
                .order_by(Analysis.id)
            ).all()

            sqlite_total = len(src_analyses)
            if sqlite_total == 0:
                return {
                    "sqlite_analyses": 0,
                    "already_in_mariadb": 0,
                    "to_insert": 0,
                    "runs_created": 0,
                    "analyses_inserted": 0,
                }

            sqlite_ids = [a.id for a in src_analyses]

            # 2. MariaDB: which of those IDs already exist?
            existing_ids: set[int] = set(
                dst.scalars(
                    select(Analysis.id).where(Analysis.id.in_(sqlite_ids))
                ).all()
            )

            # 3. Analyses to insert
            to_insert = [a for a in src_analyses if a.id not in existing_ids]
            already_count = sqlite_total - len(to_insert)

            if not to_insert:
                return {
                    "sqlite_analyses": sqlite_total,
                    "already_in_mariadb": already_count,
                    "to_insert": 0,
                    "runs_created": 0,
                    "analyses_inserted": 0,
                }

            # 4. Determine which runs need to exist in MariaDB
            needed_run_ids: set[int] = {a.run_id for a in to_insert}
            existing_run_ids: set[int] = set(
                dst.scalars(
                    select(Run.id).where(Run.id.in_(needed_run_ids))
                ).all()
            )
            missing_run_ids = needed_run_ids - existing_run_ids

            # 5. Fetch missing runs from SQLite and insert into MariaDB
            runs_created = 0
            if missing_run_ids:
                src_runs: list[Run] = src.scalars(
                    select(Run).where(Run.id.in_(missing_run_ids))
                ).all()
                for run in src_runs:
                    dst.add(Run(id=run.id, memo=run.memo, created_at=run.created_at))
                dst.flush()
                runs_created = len(src_runs)

            # 6. Insert missing analyses (preserve all fields including id)
            for row in to_insert:
                dst.add(
                    Analysis(
                        id=row.id,
                        run_id=row.run_id,
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
                )
            dst.flush()

            if dry_run:
                dst.rollback()
            else:
                dst.commit()

        return {
            "sqlite_analyses": sqlite_total,
            "already_in_mariadb": already_count,
            "to_insert": len(to_insert),
            "runs_created": runs_created,
            "analyses_inserted": len(to_insert),
        }
    finally:
        source_engine.dispose()
        target_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=PROJECT_ROOT / "greed.db",
        help="SQLite DB path (default: greed.db)",
    )
    parser.add_argument(
        "--target",
        default=os.getenv("DATABASE_URL"),
        help="MariaDB URL (default: $DATABASE_URL)",
    )
    parser.add_argument(
        "--since",
        type=date.fromisoformat,
        default=DEFAULT_SINCE,
        help="Sync analyses created on or after this date (default: 2025-05-04)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be inserted without committing",
    )
    args = parser.parse_args()

    if not args.target:
        parser.error("--target or $DATABASE_URL is required")

    result = sync(
        args.source,
        args.target,
        since=args.since,
        dry_run=args.dry_run,
    )

    action = "DRY-RUN" if args.dry_run else "COMMIT"
    print(f"[{action}] sync completed")
    print(f"  since:              {args.since}")
    print(f"  sqlite analyses:    {result['sqlite_analyses']}")
    print(f"  already in mariadb: {result['already_in_mariadb']}")
    print(f"  to insert:          {result['to_insert']}")
    print(f"  runs created:       {result['runs_created']}")
    print(f"  analyses inserted:  {result['analyses_inserted']}")


if __name__ == "__main__":
    main()
