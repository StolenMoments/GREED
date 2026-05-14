from __future__ import annotations

from collections.abc import Generator
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.korean_search import extract_korean_initials


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_PATH = PROJECT_ROOT / "greed.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def build_engine_kwargs(database_url: str) -> dict[str, Any]:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


def create_database_engine(database_url: str) -> Engine:
    return create_engine(database_url, **build_engine_kwargs(database_url))


engine = create_database_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    from backend import models  # noqa: F401

    try:
        _initialize_active_engine()
    except SQLAlchemyError as exc:
        if _is_sqlite_url(DATABASE_URL):
            raise
        _fallback_to_sqlite(exc)


def _initialize_active_engine() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate()


def _fallback_to_sqlite(exc: SQLAlchemyError) -> None:
    global engine

    failed_url = _safe_database_url(DATABASE_URL)
    fallback_url = DEFAULT_DATABASE_URL
    logger.warning(
        "Database initialization failed for %s; falling back to local SQLite at %s: %s",
        failed_url,
        DATABASE_PATH,
        exc,
    )

    engine.dispose()
    engine = create_database_engine(fallback_url)
    SessionLocal.configure(bind=engine)
    _initialize_active_engine()
    logger.info("Active database backend is sqlite: %s", DATABASE_PATH)


def _is_sqlite_url(database_url: str) -> bool:
    return make_url(database_url).get_backend_name() == "sqlite"


def _safe_database_url(database_url: str) -> str:
    return make_url(database_url).render_as_string(hide_password=True)


def _migrate() -> None:
    if engine.dialect.name == "sqlite":
        _migrate_sqlite()
    elif engine.dialect.name in ("mysql", "mariadb"):
        _migrate_mariadb()


def _migrate_sqlite() -> None:
    with engine.connect() as conn:
        jobs_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(analysis_jobs)"))]
        if "raw_markdown" not in jobs_cols:
            conn.execute(text("ALTER TABLE analysis_jobs ADD COLUMN raw_markdown TEXT"))
            conn.commit()
        if "model" not in jobs_cols:
            conn.execute(text("ALTER TABLE analysis_jobs ADD COLUMN model TEXT NOT NULL DEFAULT 'claude'"))
            conn.commit()

        analyses_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(analyses)"))]
        for col in ("entry_price_max", "target_price_max", "stop_loss_max"):
            if col not in analyses_cols:
                conn.execute(text(f"ALTER TABLE analyses ADD COLUMN {col} REAL"))
        for col, typedef in (("outcome", "VARCHAR(20)"), ("outcome_date", "DATE"), ("outcome_price", "REAL")):
            if col not in analyses_cols:
                conn.execute(text(f"ALTER TABLE analyses ADD COLUMN {col} {typedef}"))
        if "name_initials" not in analyses_cols:
            conn.execute(text("ALTER TABLE analyses ADD COLUMN name_initials TEXT NOT NULL DEFAULT ''"))
        rows = conn.execute(
            text("SELECT id, name FROM analyses WHERE name_initials IS NULL OR name_initials = ''")
        ).mappings()
        for row in rows:
            conn.execute(
                text("UPDATE analyses SET name_initials = :name_initials WHERE id = :id"),
                {
                    "id": row["id"],
                    "name_initials": extract_korean_initials(row["name"] or ""),
                },
            )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_analyses_name_initials ON analyses(name_initials)")
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS us_stocks (
                    code VARCHAR(20) PRIMARY KEY,
                    name VARCHAR(150) NOT NULL,
                    market VARCHAR(20) NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_us_stocks_name ON us_stocks(name)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_us_stocks_market ON us_stocks(market)"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS price_bars (
                    ticker VARCHAR(20) NOT NULL,
                    interval VARCHAR(2) NOT NULL,
                    bar_date DATE NOT NULL,
                    open REAL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL,
                    volume REAL,
                    trading_value REAL,
                    fetched_at DATETIME NOT NULL,
                    PRIMARY KEY (ticker, interval, bar_date)
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_price_bars_lookup "
                "ON price_bars(ticker, interval, bar_date)"
            )
        )
        conn.commit()

        # Backfill price fields for analyses created before price extraction was added
        _backfill_prices(conn)


def _migrate_mariadb() -> None:
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


def _backfill_prices(conn: Any) -> None:
    from backend.parser import parse_markdown

    rows = list(
        conn.execute(
            text(
                "SELECT id, markdown FROM analyses"
                " WHERE entry_price IS NULL AND target_price IS NULL AND stop_loss IS NULL"
                " AND markdown IS NOT NULL AND markdown != ''"
            )
        ).mappings()
    )
    if not rows:
        return

    for row in rows:
        result = parse_markdown(row["markdown"])
        conn.execute(
            text(
                "UPDATE analyses SET"
                " entry_price = :entry_price,"
                " entry_price_max = :entry_price_max,"
                " target_price = :target_price,"
                " target_price_max = :target_price_max,"
                " stop_loss = :stop_loss,"
                " stop_loss_max = :stop_loss_max"
                " WHERE id = :id"
            ),
            {
                "id": row["id"],
                "entry_price": result.data.get("entry_price"),
                "entry_price_max": result.data.get("entry_price_max"),
                "target_price": result.data.get("target_price"),
                "target_price_max": result.data.get("target_price_max"),
                "stop_loss": result.data.get("stop_loss"),
                "stop_loss_max": result.data.get("stop_loss_max"),
            },
        )
    conn.commit()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
