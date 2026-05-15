from __future__ import annotations

from collections.abc import Generator
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError  # noqa: F401 — re-exported for tests
from sqlalchemy.orm import Session, declarative_base, sessionmaker


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL: str = os.getenv("DATABASE_URL", "")


def build_engine_kwargs(database_url: str) -> dict[str, Any]:
    return {"pool_pre_ping": True}


def create_database_engine(database_url: str) -> Engine:
    return create_engine(database_url, **build_engine_kwargs(database_url))


engine: Engine | None = create_database_engine(DATABASE_URL) if DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    global engine

    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is required")
    if make_url(DATABASE_URL).get_backend_name() == "sqlite":
        raise RuntimeError(
            "SQLite is not supported; set DATABASE_URL to a MariaDB connection string"
        )

    if engine is None:
        engine = create_database_engine(DATABASE_URL)
        SessionLocal.configure(bind=engine)

    from backend import models  # noqa: F401

    _initialize_active_engine()


def _initialize_active_engine() -> None:
    assert engine is not None
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate() -> None:
    assert engine is not None
    if engine.dialect.name in ("mysql", "mariadb"):
        _migrate_mariadb()


def _migrate_mariadb() -> None:
    assert engine is not None
    with engine.connect() as conn:
        for col, typedef in [
            ("outcome", "VARCHAR(20)"),
            ("outcome_date", "DATE"),
            ("outcome_price", "FLOAT"),
        ]:
            conn.execute(text(f"ALTER TABLE analyses ADD COLUMN IF NOT EXISTS {col} {typedef}"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS price_bars (
                    ticker VARCHAR(20) NOT NULL,
                    interval VARCHAR(2) NOT NULL,
                    bar_date DATE NOT NULL,
                    open FLOAT NULL,
                    high FLOAT NOT NULL,
                    low FLOAT NOT NULL,
                    close FLOAT NULL,
                    volume FLOAT NULL,
                    trading_value FLOAT NULL,
                    fetched_at DATETIME NOT NULL,
                    PRIMARY KEY (ticker, interval, bar_date),
                    INDEX ix_price_bars_lookup (ticker, interval, bar_date)
                )
                """
            )
        )
        conn.commit()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
