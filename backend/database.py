from __future__ import annotations

from collections.abc import Generator
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError  # noqa: F401 — re-exported for tests
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.timezone import seoul_now


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL: str = os.getenv("DATABASE_URL", "")
DATABASE_UNAVAILABLE_MESSAGE = "데이터베이스 연결이 끊겼습니다. 터널을 확인하고 잠시 후 다시 시도하세요."
_INITIALIZE_LOCK = Lock()
_is_initialized = False


def build_engine_kwargs(database_url: str) -> dict[str, Any]:
    return {"pool_pre_ping": True}


def create_database_engine(database_url: str) -> Engine:
    return create_engine(database_url, **build_engine_kwargs(database_url))


engine: Engine | None = create_database_engine(DATABASE_URL) if DATABASE_URL else None
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    ensure_database_ready()


def ensure_database_ready() -> None:
    global engine, _is_initialized

    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is required")
    if make_url(DATABASE_URL).get_backend_name() not in {"mysql", "mariadb"}:
        raise RuntimeError(
            "Unsupported database backend; set DATABASE_URL to a MariaDB connection string"
        )

    if engine is None:
        engine = create_database_engine(DATABASE_URL)
        SessionLocal.configure(bind=engine)

    if _is_initialized:
        return

    with _INITIALIZE_LOCK:
        if _is_initialized:
            return
        try:
            from backend import models  # noqa: F401

            _initialize_active_engine()
            _is_initialized = True
        except (DBAPIError, OperationalError):
            dispose_engine()
            raise


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
        for tbl in [
            "analyses", "analysis_jobs", "backtest_runs",
            "analysis_backtest_jobs", "backtest_signals", "backtest_stats",
            "backtest_universe_members", "backtest_preload_jobs",
            "backtest_strategy_jobs", "daily_rally_rule_stats",
            "daily_rally_pattern_stats", "daily_rally_current_candidates",
        ]:
            rows = conn.execute(text(
                "SELECT CONSTRAINT_NAME FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                f"AND TABLE_NAME = '{tbl}' AND CONSTRAINT_TYPE = 'FOREIGN KEY'"
            )).all()
            for row in rows:
                conn.execute(text(f"ALTER TABLE `{tbl}` DROP FOREIGN KEY `{row[0]}`"))
        conn.commit()

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
                    `interval` VARCHAR(2) NOT NULL,
                    bar_date DATE NOT NULL,
                    open FLOAT NULL,
                    high FLOAT NOT NULL,
                    low FLOAT NOT NULL,
                    close FLOAT NULL,
                    volume FLOAT NULL,
                    trading_value FLOAT NULL,
                    fetched_at DATETIME NOT NULL,
                    PRIMARY KEY (ticker, `interval`, bar_date),
                    INDEX ix_price_bars_lookup (ticker, `interval`, bar_date)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS backtest_runs (
                    id INTEGER NOT NULL AUTO_INCREMENT,
                    created_at DATETIME NOT NULL,
                    universe VARCHAR(50) NOT NULL,
                    buy_threshold INTEGER NOT NULL,
                    horizons VARCHAR(50) NOT NULL,
                    warmup_weeks INTEGER NOT NULL,
                    data_start DATE NULL,
                    data_end DATE NULL,
                    ticker_count INTEGER NOT NULL,
                    signal_count INTEGER NOT NULL,
                    notes TEXT NULL,
                    PRIMARY KEY (id)
                )
                """
            )
        )
        for col, typedef in [
            ("source_analysis_id", "INTEGER NULL"),
            ("strategy_kind", "VARCHAR(50) NULL"),
            ("similarity_threshold", "INTEGER NULL"),
        ]:
            conn.execute(text(f"ALTER TABLE backtest_runs ADD COLUMN IF NOT EXISTS {col} {typedef}"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS backtest_universe_members (
                    ticker VARCHAR(20) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    market VARCHAR(20) NOT NULL DEFAULT 'KR',
                    active BOOL NOT NULL DEFAULT TRUE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    source VARCHAR(50) NOT NULL DEFAULT 'manual',
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    PRIMARY KEY (ticker),
                    INDEX ix_backtest_universe_members_active_order (active, sort_order, ticker)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS backtest_preload_jobs (
                    id INTEGER NOT NULL AUTO_INCREMENT,
                    ticker VARCHAR(20) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    processed INTEGER NOT NULL DEFAULT 0,
                    skipped INTEGER NOT NULL DEFAULT 0,
                    upserted_rows INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT NULL,
                    created_at DATETIME NOT NULL,
                    completed_at DATETIME NULL,
                    PRIMARY KEY (id),
                    INDEX ix_backtest_preload_jobs_status_created (status, created_at)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS backtest_signals (
                    id INTEGER NOT NULL AUTO_INCREMENT,
                    run_id INTEGER NOT NULL,
                    ticker VARCHAR(20) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    signal_date DATE NOT NULL,
                    score INTEGER NOT NULL,
                    score_bucket VARCHAR(10) NOT NULL,
                    entry_date DATE NULL,
                    entry_price FLOAT NOT NULL,
                    ret_4w FLOAT NULL,
                    ret_8w FLOAT NULL,
                    ret_12w FLOAT NULL,
                    ret_26w FLOAT NULL,
                    exit_date DATE NULL,
                    exit_reason VARCHAR(20) NULL,
                    exit_price FLOAT NULL,
                    event_return FLOAT NULL,
                    days_held INTEGER NULL,
                    PRIMARY KEY (id),
                    INDEX ix_backtest_signals_run (run_id),
                    INDEX ix_backtest_signals_run_bucket (run_id, score_bucket)
                )
                """
            )
        )
        conn.execute(text("ALTER TABLE backtest_signals MODIFY COLUMN entry_date DATE NULL"))
        for col, typedef in [
            ("exit_date", "DATE NULL"),
            ("exit_reason", "VARCHAR(20) NULL"),
            ("exit_price", "FLOAT NULL"),
            ("event_return", "FLOAT NULL"),
            ("days_held", "INTEGER NULL"),
        ]:
            conn.execute(text(f"ALTER TABLE backtest_signals ADD COLUMN IF NOT EXISTS {col} {typedef}"))
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS backtest_stats (
                    run_id INTEGER NOT NULL,
                    horizon INTEGER NOT NULL,
                    score_bucket VARCHAR(10) NOT NULL,
                    count INTEGER NOT NULL,
                    censored_count INTEGER NOT NULL,
                    win_rate FLOAT NULL,
                    mean FLOAT NULL,
                    median FLOAT NULL,
                    std FLOAT NULL,
                    p25 FLOAT NULL,
                    p75 FLOAT NULL,
                    min FLOAT NULL,
                    max FLOAT NULL,
                    PRIMARY KEY (run_id, horizon, score_bucket)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS daily_rally_rule_stats (
                    id INTEGER NOT NULL AUTO_INCREMENT,
                    run_id INTEGER NOT NULL,
                    rule_key VARCHAR(255) NOT NULL,
                    rule_label VARCHAR(500) NOT NULL,
                    support INTEGER NOT NULL,
                    positives INTEGER NOT NULL,
                    total_matches INTEGER NOT NULL,
                    `precision` FLOAT NOT NULL,
                    base_rate FLOAT NOT NULL,
                    lift FLOAT NOT NULL,
                    score FLOAT NOT NULL,
                    PRIMARY KEY (id),
                    INDEX ix_daily_rally_rule_stats_run_score (run_id, score)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS daily_rally_current_candidates (
                    id INTEGER NOT NULL AUTO_INCREMENT,
                    run_id INTEGER NOT NULL,
                    ticker VARCHAR(20) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    signal_date DATE NOT NULL,
                    close_price FLOAT NOT NULL,
                    matched_rules_json TEXT NOT NULL,
                    matched_rule_count INTEGER NOT NULL,
                    max_rule_score FLOAT NULL,
                    mean_rule_score FLOAT NULL,
                    features_json TEXT NOT NULL,
                    PRIMARY KEY (id),
                    INDEX ix_daily_rally_current_candidates_run_score (run_id, max_rule_score),
                    INDEX ix_daily_rally_current_candidates_run_ticker (run_id, ticker)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS daily_rally_pattern_stats (
                    id INTEGER NOT NULL AUTO_INCREMENT,
                    run_id INTEGER NOT NULL,
                    pattern_key VARCHAR(255) NOT NULL,
                    pattern_label VARCHAR(500) NOT NULL,
                    support INTEGER NOT NULL,
                    positives INTEGER NOT NULL,
                    total_matches INTEGER NOT NULL,
                    `precision` FLOAT NOT NULL,
                    base_rate FLOAT NOT NULL,
                    lift FLOAT NOT NULL,
                    score FLOAT NOT NULL,
                    return_stats_json TEXT NOT NULL,
                    PRIMARY KEY (id),
                    INDEX ix_daily_rally_pattern_stats_run_score (run_id, score)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS analysis_backtest_jobs (
                    id INTEGER NOT NULL AUTO_INCREMENT,
                    analysis_id INTEGER NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    similarity_threshold INTEGER NOT NULL,
                    backtest_run_id INTEGER NULL,
                    error_message TEXT NULL,
                    created_at DATETIME NOT NULL,
                    completed_at DATETIME NULL,
                    PRIMARY KEY (id),
                    INDEX ix_analysis_backtest_jobs_analysis_created (analysis_id, created_at),
                    INDEX ix_analysis_backtest_jobs_status_created (status, created_at)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS backtest_strategy_jobs (
                    id INTEGER NOT NULL AUTO_INCREMENT,
                    strategy_kind VARCHAR(50) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    backtest_run_id INTEGER NULL,
                    error_message TEXT NULL,
                    created_at DATETIME NOT NULL,
                    completed_at DATETIME NULL,
                    PRIMARY KEY (id),
                    INDEX ix_backtest_strategy_jobs_status_created (status, created_at)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fundamental_snapshots (
                    ticker VARCHAR(20) NOT NULL,
                    snapshot_date DATE NOT NULL,
                    per FLOAT NULL,
                    pbr FLOAT NULL,
                    eps FLOAT NULL,
                    bps FLOAT NULL,
                    div_yield FLOAT NULL,
                    market_cap FLOAT NULL,
                    fetched_at DATETIME NOT NULL,
                    PRIMARY KEY (ticker)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fundamental_history (
                    ticker VARCHAR(20) NOT NULL,
                    snapshot_date DATE NOT NULL,
                    per FLOAT NULL,
                    pbr FLOAT NULL,
                    eps FLOAT NULL,
                    bps FLOAT NULL,
                    div_yield FLOAT NULL,
                    fetched_at DATETIME NOT NULL,
                    PRIMARY KEY (ticker, snapshot_date),
                    INDEX ix_fundamental_history_lookup (ticker, snapshot_date)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS current_candidates (
                    id INTEGER NOT NULL AUTO_INCREMENT,
                    analysis_id INTEGER NOT NULL,
                    scan_date DATE NOT NULL,
                    ticker VARCHAR(20) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    score INTEGER NOT NULL,
                    current_close FLOAT NOT NULL,
                    entry_price FLOAT NOT NULL,
                    target_price FLOAT NOT NULL,
                    stop_price FLOAT NOT NULL,
                    entry_gap_pct FLOAT NOT NULL,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    INDEX ix_current_candidates_lookup (analysis_id, scan_date),
                    UNIQUE KEY uq_current_candidates_key (analysis_id, scan_date, ticker)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS candidate_scan_jobs (
                    id INTEGER NOT NULL AUTO_INCREMENT,
                    analysis_id INTEGER NOT NULL,
                    threshold INTEGER NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    candidate_count INTEGER NULL,
                    scan_date DATE NULL,
                    error_message TEXT NULL,
                    created_at DATETIME NOT NULL,
                    completed_at DATETIME NULL,
                    PRIMARY KEY (id),
                    INDEX ix_candidate_scan_jobs_status_created (status, created_at),
                    INDEX ix_candidate_scan_jobs_analysis_created (analysis_id, created_at)
                )
                """
            )
        )
        conn.commit()


def dispose_engine() -> None:
    if engine is not None:
        engine.dispose()


def mark_database_unavailable(exc: BaseException) -> None:
    logger.warning("Database connection unavailable: %s", exc)
    dispose_engine()


def is_database_unavailable_error(exc: BaseException) -> bool:
    return isinstance(exc, OperationalError) or (
        isinstance(exc, DBAPIError) and exc.connection_invalidated
    )


def get_database_health() -> dict[str, str]:
    try:
        ensure_database_ready()
        assert engine is not None
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "up", "checked_at": _health_checked_at()}
    except (DBAPIError, OperationalError) as exc:
        mark_database_unavailable(exc)
        return {"status": "down", "checked_at": _health_checked_at()}
    except RuntimeError as exc:
        logger.warning("Database health check failed: %s", exc)
        return {"status": "down", "checked_at": _health_checked_at()}


def _health_checked_at() -> str:
    return seoul_now().isoformat()


def get_db() -> Generator[Session, None, None]:
    try:
        ensure_database_ready()
    except (DBAPIError, OperationalError) as exc:
        mark_database_unavailable(exc)
        raise

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
