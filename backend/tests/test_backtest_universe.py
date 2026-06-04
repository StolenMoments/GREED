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
from scripts.backtest.sync_kosdaq150 import (  # noqa: E402
    KOSDAQ150_SOURCE,
    fetch_kosdaq150_members,
    sync_kosdaq150_members,
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


class FakeKosdaq150StockClient:
    def __init__(self, members: list[str] | None = None):
        self.members = members or [f"{ticker:06d}" for ticker in range(1, 151)]

    def get_index_ticker_list(self, date: str, market: str):
        assert date == "20260604"
        assert market == "KOSDAQ"
        return ["2001", "2002"]

    def get_index_ticker_name(self, index_code: str):
        return {"2001": "코스닥 150", "2002": "Other Index"}[index_code]

    def get_index_portfolio_deposit_file(
        self,
        index_code: str,
        date: str,
        alternative: bool = False,
    ):
        assert index_code == "2001"
        assert date == "20260604"
        assert alternative is True
        return self.members

    def get_market_ticker_name(self, ticker: str):
        return f"Name {ticker}"


def test_fetch_kosdaq150_members_returns_150_named_members():
    rows = fetch_kosdaq150_members("20260604", stock_client=FakeKosdaq150StockClient())

    assert len(rows) == 150
    assert rows[0] == ("000001", "Name 000001")
    assert rows[-1] == ("000150", "Name 000150")


def test_fetch_kosdaq150_members_accepts_six_character_krx_codes():
    members = ["0009K0"] + [f"{ticker:06d}" for ticker in range(1, 150)]

    rows = fetch_kosdaq150_members(
        "20260604",
        stock_client=FakeKosdaq150StockClient(members),
    )

    assert rows[0] == ("0009K0", "Name 0009K0")


def test_sync_kosdaq150_members_inserts_active_auto_source_rows(db_session):
    count = sync_kosdaq150_members(
        db_session,
        "20260604",
        stock_client=FakeKosdaq150StockClient(),
    )

    rows = db_session.query(BacktestUniverseMember).order_by(BacktestUniverseMember.ticker).all()
    assert count == 150
    assert len(rows) == 150
    assert all(row.active is True for row in rows)
    assert all(row.source == KOSDAQ150_SOURCE for row in rows)
    assert rows[0].ticker == "000001"
    assert rows[0].sort_order == 0
    assert rows[-1].ticker == "000150"
    assert rows[-1].sort_order == 149


def test_sync_kosdaq150_members_reactivates_existing_matching_ticker(db_session):
    db_session.add(
        BacktestUniverseMember(
            ticker="000001",
            name="Old Name",
            market="KR",
            active=False,
            sort_order=12,
            source="manual",
        )
    )
    db_session.commit()

    count = sync_kosdaq150_members(
        db_session,
        "20260604",
        stock_client=FakeKosdaq150StockClient(),
    )

    existing = db_session.get(BacktestUniverseMember, "000001")
    assert count == 150
    assert existing is not None
    assert existing.name == "Name 000001"
    assert existing.active is True
    assert existing.source == KOSDAQ150_SOURCE
    assert existing.sort_order == 12


def test_sync_kosdaq150_members_non_150_count_raises_without_commit(db_session):
    db_session.add(
        BacktestUniverseMember(
            ticker="999999",
            name="Existing",
            market="KR",
            active=True,
            sort_order=3,
            source="manual",
        )
    )
    db_session.commit()

    with pytest.raises(ValueError, match="Expected 150 KOSDAQ150 members"):
        sync_kosdaq150_members(
            db_session,
            "20260604",
            stock_client=FakeKosdaq150StockClient(["000001", "000002"]),
        )

    rows = db_session.query(BacktestUniverseMember).all()
    assert [(row.ticker, row.name, row.source) for row in rows] == [
        ("999999", "Existing", "manual")
    ]
