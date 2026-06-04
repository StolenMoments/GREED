import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base
from backend.models import BacktestUniverseMember
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from backtest.universe import (  # noqa: E402
    ensure_default_universe_seeded,
    import_universe_csv,
    load_active_universe,
    load_universe,
)


def test_load_universe_parses_code_name(tmp_path):
    csv = tmp_path / "u.csv"
    csv.write_text(
        "code,name\n5930,삼성전자\n000660,SK하이닉스\n",
        encoding="utf-8-sig",
    )

    rows = load_universe(csv)

    assert rows == [("005930", "삼성전자"), ("000660", "SK하이닉스")]


def test_load_universe_accepts_alphanumeric_krx_tickers(tmp_path):
    csv = tmp_path / "u.csv"
    csv.write_text("code,name\nA12345,Alpha KRX\nABCDEF,Letters Only\n", encoding="utf-8-sig")

    rows = load_universe(csv)

    assert rows == [("A12345", "Alpha KRX")]


def test_load_universe_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_universe(tmp_path / "nope.csv")


def test_load_universe_empty_raises(tmp_path):
    csv = tmp_path / "u.csv"
    csv.write_text("code,name\n", encoding="utf-8-sig")

    with pytest.raises(ValueError):
        load_universe(csv)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_load_active_universe_returns_active_members_in_sort_order(db_session):
    db_session.add_all(
        [
            BacktestUniverseMember(
                ticker="000660",
                name="SK Hynix",
                market="KR",
                active=True,
                sort_order=2,
                source="test",
            ),
            BacktestUniverseMember(
                ticker="005930",
                name="Samsung",
                market="KR",
                active=True,
                sort_order=1,
                source="test",
            ),
            BacktestUniverseMember(
                ticker="035420",
                name="Naver",
                market="KR",
                active=False,
                sort_order=0,
                source="test",
            ),
        ]
    )
    db_session.commit()

    assert load_active_universe(db_session) == [
        ("005930", "Samsung"),
        ("000660", "SK Hynix"),
    ]


def test_load_active_universe_empty_raises_clear_error(db_session):
    with pytest.raises(ValueError, match="No active backtest universe members"):
        load_active_universe(db_session)


def test_import_universe_csv_upserts_normalizes_and_reactivates(db_session, tmp_path):
    csv = tmp_path / "u.csv"
    csv.write_text("code,name\n5930,Samsung\n000660,SK Hynix\n", encoding="utf-8-sig")
    db_session.add(
        BacktestUniverseMember(
            ticker="005930",
            name="Old Samsung",
            market="KR",
            active=False,
            sort_order=99,
            source="manual",
        )
    )
    db_session.commit()

    imported = import_universe_csv(db_session, csv, source="seed")

    assert imported == 2
    samsung = db_session.get(BacktestUniverseMember, "005930")
    hynix = db_session.get(BacktestUniverseMember, "000660")
    assert samsung is not None
    assert samsung.name == "Samsung"
    assert samsung.active is True
    assert samsung.sort_order == 0
    assert samsung.source == "seed"
    assert hynix is not None
    assert hynix.sort_order == 1


def test_ensure_default_universe_seeded_imports_when_empty(db_session, tmp_path):
    csv = tmp_path / "u.csv"
    csv.write_text("code,name\n5930,Samsung\n000660,SK Hynix\n", encoding="utf-8-sig")

    imported = ensure_default_universe_seeded(db_session, csv)

    assert imported == 2
    assert load_active_universe(db_session) == [
        ("005930", "Samsung"),
        ("000660", "SK Hynix"),
    ]


def test_ensure_default_universe_seeded_preserves_existing_members(db_session, tmp_path):
    csv = tmp_path / "u.csv"
    csv.write_text("code,name\n5930,Samsung\n000660,SK Hynix\n", encoding="utf-8-sig")
    db_session.add(
        BacktestUniverseMember(
            ticker="005930",
            name="User Samsung",
            market="KR",
            active=False,
            sort_order=7,
            source="manual",
        )
    )
    db_session.commit()

    imported = ensure_default_universe_seeded(db_session, csv)

    samsung = db_session.get(BacktestUniverseMember, "005930")
    assert imported == 0
    assert samsung is not None
    assert samsung.name == "User Samsung"
    assert samsung.active is False
    assert samsung.sort_order == 7
    assert samsung.source == "manual"
