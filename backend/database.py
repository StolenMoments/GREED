from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.korean_search import extract_korean_initials


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "greed.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    from backend import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate() -> None:
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
        conn.commit()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
