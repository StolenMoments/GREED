from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy import inspect

import backend.database as database
from backend.database import build_engine_kwargs


@pytest.fixture(autouse=True)
def restore_database_state() -> Generator[None, None, None]:
    original_database_url = database.DATABASE_URL
    original_default_database_url = database.DEFAULT_DATABASE_URL
    original_database_path = database.DATABASE_PATH
    original_engine = database.engine
    original_bind = database.SessionLocal.kw.get("bind")

    yield

    database.DATABASE_URL = original_database_url
    database.DEFAULT_DATABASE_URL = original_default_database_url
    database.DATABASE_PATH = original_database_path
    database.engine = original_engine
    database.SessionLocal.configure(bind=original_bind)


def test_build_engine_kwargs_keeps_sqlite_thread_check_disabled() -> None:
    assert build_engine_kwargs("sqlite:///greed.db") == {
        "connect_args": {"check_same_thread": False}
    }


def test_build_engine_kwargs_enables_pre_ping_for_mariadb() -> None:
    assert build_engine_kwargs(
        "mysql+pymysql://greed:secret@example.com:3306/greed?charset=utf8mb4"
    ) == {"pool_pre_ping": True}


def test_init_db_falls_back_to_sqlite_when_configured_database_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original_session_local = database.SessionLocal
    initial_engine = create_engine("sqlite:///:memory:")
    fallback_path = tmp_path / "fallback.db"
    fallback_url = f"sqlite:///{fallback_path.as_posix()}"
    create_all_binds: list[str] = []
    migrated_backends: list[str] = []

    monkeypatch.setattr(
        database,
        "DATABASE_URL",
        "mysql+pymysql://greed:secret@example.com:3306/greed?charset=utf8mb4",
    )
    monkeypatch.setattr(database, "DEFAULT_DATABASE_URL", fallback_url)
    monkeypatch.setattr(database, "DATABASE_PATH", fallback_path)
    monkeypatch.setattr(database, "engine", initial_engine)
    database.SessionLocal.configure(bind=initial_engine)
    monkeypatch.setattr(
        database,
        "_migrate_sqlite",
        lambda: migrated_backends.append(database.engine.dialect.name),
    )

    def fake_create_all(*, bind: object) -> None:
        create_all_binds.append(str(bind.url))  # type: ignore[attr-defined]
        if bind is initial_engine:
            raise OperationalError("SELECT 1", {}, Exception("database is down"))

    monkeypatch.setattr(database.Base.metadata, "create_all", fake_create_all)

    database.init_db()

    assert database.SessionLocal is original_session_local
    assert create_all_binds == ["sqlite:///:memory:", fallback_url]
    assert database.engine.dialect.name == "sqlite"
    assert migrated_backends == ["sqlite"]


def test_init_db_does_not_fallback_when_sqlite_initialization_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sqlite_url = f"sqlite:///{(tmp_path / 'broken.db').as_posix()}"
    sqlite_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    created_urls: list[str] = []

    monkeypatch.setattr(database, "DATABASE_URL", sqlite_url)
    monkeypatch.setattr(database, "engine", sqlite_engine)
    database.SessionLocal.configure(bind=sqlite_engine)
    monkeypatch.setattr(
        database,
        "create_database_engine",
        lambda url: created_urls.append(url) or create_engine(url),
    )

    def fake_create_all(*, bind: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception("sqlite init failed"))

    monkeypatch.setattr(database.Base.metadata, "create_all", fake_create_all)

    with pytest.raises(OperationalError, match="sqlite init failed"):
        database.init_db()

    assert created_urls == []


def test_migrate_sqlite_creates_price_bars_table(monkeypatch: pytest.MonkeyPatch) -> None:
    sqlite_engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(database, "engine", sqlite_engine)

    database.Base.metadata.create_all(bind=sqlite_engine)
    database._migrate_sqlite()

    inspector = inspect(sqlite_engine)
    assert "price_bars" in inspector.get_table_names()
    assert "ix_price_bars_lookup" in {
        index["name"] for index in inspector.get_indexes("price_bars")
    }

    sqlite_engine.dispose()


def test_migrate_mariadb_creates_price_bars_table(monkeypatch: pytest.MonkeyPatch) -> None:
    statements: list[str] = []

    class FakeConnection:
        def __enter__(self) -> "FakeConnection":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def execute(self, statement: object) -> None:
            statements.append(str(statement))

        def commit(self) -> None:
            return None

    class FakeEngine:
        def connect(self) -> FakeConnection:
            return FakeConnection()

    monkeypatch.setattr(database, "engine", FakeEngine())

    database._migrate_mariadb()

    assert any("CREATE TABLE IF NOT EXISTS price_bars" in statement for statement in statements)
    assert any("INDEX ix_price_bars_lookup" in statement for statement in statements)
