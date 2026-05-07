"""Migrate the local SQLite greed.db into a fresh MariaDB database.

The target database must be empty. Primary keys are preserved so foreign key
links remain identical after the migration.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from backend.database import Base
from backend.models import Analysis, AnalysisJob, KrxStock, Run, StockPrice, UsStock


TABLE_MODELS = (Run, Analysis, AnalysisJob, StockPrice, KrxStock, UsStock)


def _sqlite_engine(db_path: Path) -> Engine:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {db_path}")
    return create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )


def _target_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


def _quote_mysql_identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def create_mysql_database(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() not in {"mysql", "mariadb"}:
        raise ValueError("--create-schema is only supported for MySQL/MariaDB URLs")
    if not url.database:
        raise ValueError("Target DATABASE_URL must include a database name")

    server_url = url.set(database="")
    server_engine = create_engine(server_url, pool_pre_ping=True)
    try:
        database_name = _quote_mysql_identifier(url.database)
        with server_engine.begin() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS {database_name} "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
    finally:
        server_engine.dispose()


def _session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _table_name(model: type[object]) -> str:
    return model.__tablename__


def _managed_table_names() -> list[str]:
    return [_table_name(model) for model in TABLE_MODELS]


def _assert_target_empty(engine: Engine) -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    non_empty: list[str] = []
    with engine.connect() as conn:
        for table_name in _managed_table_names():
            if table_name not in existing_tables:
                continue
            count = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
            if count:
                non_empty.append(f"{table_name}={count}")
    if non_empty:
        raise RuntimeError(
            "Target database is not empty for managed tables: " + ", ".join(non_empty)
        )


def _copy_runs(src: Session, dst: Session) -> int:
    rows = src.scalars(select(Run).order_by(Run.id)).all()
    dst.add_all(
        Run(id=row.id, memo=row.memo, created_at=row.created_at)
        for row in rows
    )
    return len(rows)


def _copy_analyses(src: Session, dst: Session) -> int:
    rows = src.scalars(select(Analysis).order_by(Analysis.id)).all()
    dst.add_all(
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
        for row in rows
    )
    return len(rows)


def _copy_analysis_jobs(src: Session, dst: Session) -> int:
    rows = src.scalars(select(AnalysisJob).order_by(AnalysisJob.id)).all()
    dst.add_all(
        AnalysisJob(
            id=row.id,
            ticker=row.ticker,
            run_id=row.run_id,
            model=row.model,
            status=row.status,
            error_message=row.error_message,
            raw_markdown=row.raw_markdown,
            analysis_id=row.analysis_id,
            created_at=row.created_at,
        )
        for row in rows
    )
    return len(rows)


def _copy_stock_prices(src: Session, dst: Session) -> int:
    rows = src.scalars(select(StockPrice).order_by(StockPrice.ticker)).all()
    dst.add_all(
        StockPrice(
            ticker=row.ticker,
            price_date=row.price_date,
            close_price=row.close_price,
            fetched_at=row.fetched_at,
        )
        for row in rows
    )
    return len(rows)


def _copy_krx_stocks(src: Session, dst: Session) -> int:
    rows = src.scalars(select(KrxStock).order_by(KrxStock.code)).all()
    dst.add_all(
        KrxStock(
            code=row.code,
            name=row.name,
            name_initials=row.name_initials,
            updated_at=row.updated_at,
        )
        for row in rows
    )
    return len(rows)


def _copy_us_stocks(src: Session, dst: Session) -> int:
    rows = src.scalars(select(UsStock).order_by(UsStock.code)).all()
    dst.add_all(
        UsStock(
            code=row.code,
            name=row.name,
            market=row.market,
            updated_at=row.updated_at,
        )
        for row in rows
    )
    return len(rows)


def _count_rows(engine: Engine) -> dict[str, int]:
    counts: dict[str, int] = {}
    with engine.connect() as conn:
        for table_name in _managed_table_names():
            counts[table_name] = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
    return counts


def _assert_counts(source_engine: Engine, target_engine: Engine, expected: dict[str, int]) -> None:
    source_counts = _count_rows(source_engine)
    target_counts = _count_rows(target_engine)
    for table_name, expected_count in expected.items():
        if source_counts[table_name] != expected_count:
            raise RuntimeError(
                f"Source count changed during migration: {table_name} "
                f"expected {expected_count}, got {source_counts[table_name]}"
            )
        if target_counts[table_name] != expected_count:
            raise RuntimeError(
                f"Target count mismatch: {table_name} expected {expected_count}, "
                f"got {target_counts[table_name]}"
            )


def _assert_foreign_keys(engine: Engine) -> None:
    checks = {
        "analyses.run_id": """
            SELECT COUNT(*)
            FROM analyses a
            LEFT JOIN runs r ON a.run_id = r.id
            WHERE r.id IS NULL
        """,
        "analysis_jobs.run_id": """
            SELECT COUNT(*)
            FROM analysis_jobs j
            LEFT JOIN runs r ON j.run_id = r.id
            WHERE r.id IS NULL
        """,
        "analysis_jobs.analysis_id": """
            SELECT COUNT(*)
            FROM analysis_jobs j
            LEFT JOIN analyses a ON j.analysis_id = a.id
            WHERE j.analysis_id IS NOT NULL AND a.id IS NULL
        """,
    }
    with engine.connect() as conn:
        invalid: list[str] = []
        for name, sql in checks.items():
            count = conn.execute(text(sql)).scalar_one()
            if count:
                invalid.append(f"{name}={count}")
    if invalid:
        raise RuntimeError("Foreign key validation failed: " + ", ".join(invalid))


def migrate(source_path: Path, target_url: str, *, create_schema: bool, dry_run: bool) -> dict[str, int]:
    if create_schema:
        create_mysql_database(target_url)

    source_engine = _sqlite_engine(source_path)
    target_engine = _target_engine(target_url)
    try:
        Base.metadata.create_all(bind=target_engine)
        _assert_target_empty(target_engine)

        SourceSession = _session_factory(source_engine)
        TargetSession = _session_factory(target_engine)
        with SourceSession() as src, TargetSession() as dst:
            counts = {}
            for table_name, copy_rows in (
                ("runs", _copy_runs),
                ("analyses", _copy_analyses),
                ("analysis_jobs", _copy_analysis_jobs),
                ("stock_prices", _copy_stock_prices),
                ("krx_stocks", _copy_krx_stocks),
                ("us_stocks", _copy_us_stocks),
            ):
                counts[table_name] = copy_rows(src, dst)
                dst.flush()
            if dry_run:
                dst.rollback()
                return counts
            dst.commit()

        _assert_counts(source_engine, target_engine, counts)
        _assert_foreign_keys(target_engine)
        return counts
    finally:
        source_engine.dispose()
        target_engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=PROJECT_ROOT / "greed.db")
    parser.add_argument("--target", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--create-schema", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.target:
        parser.error("--target or DATABASE_URL is required")

    counts = migrate(
        args.source,
        args.target,
        create_schema=args.create_schema,
        dry_run=args.dry_run,
    )
    action = "DRY-RUN" if args.dry_run else "COMMIT"
    print(f"[{action}] migration completed")
    for table_name in _managed_table_names():
        print(f"  - {table_name}: {counts[table_name]}")


if __name__ == "__main__":
    main()
