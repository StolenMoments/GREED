from __future__ import annotations

from backend.database import build_engine_kwargs


def test_build_engine_kwargs_keeps_sqlite_thread_check_disabled() -> None:
    assert build_engine_kwargs("sqlite:///greed.db") == {
        "connect_args": {"check_same_thread": False}
    }


def test_build_engine_kwargs_enables_pre_ping_for_mariadb() -> None:
    assert build_engine_kwargs(
        "mysql+pymysql://greed:secret@example.com:3306/greed?charset=utf8mb4"
    ) == {"pool_pre_ping": True}
