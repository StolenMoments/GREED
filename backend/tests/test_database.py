from __future__ import annotations

from collections.abc import Generator

import pytest

import backend.database as database
from backend.database import build_engine_kwargs


@pytest.fixture(autouse=True)
def restore_database_state() -> Generator[None, None, None]:
    original_database_url = database.DATABASE_URL
    original_engine = database.engine
    original_bind = database.SessionLocal.kw.get("bind")
    original_is_initialized = database._is_initialized

    yield

    database.DATABASE_URL = original_database_url
    database.engine = original_engine
    database._is_initialized = original_is_initialized
    database.SessionLocal.configure(bind=original_bind)


def test_build_engine_kwargs_enables_pre_ping_for_mariadb() -> None:
    assert build_engine_kwargs(
        "mysql+pymysql://greed:secret@example.com:3306/greed?charset=utf8mb4"
    ) == {"pool_pre_ping": True}


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
