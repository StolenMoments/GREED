from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.models import KrxStock, UsStock
from backend.routers import tickers
from backend.timezone import seoul_now


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    app = FastAPI()
    app.include_router(tickers.router)

    def override_get_db() -> Generator[Session, None, None]:
        session = testing_session_local()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        test_client.app.state.testing_session_local = testing_session_local
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(client: TestClient) -> Generator[Session, None, None]:
    session_factory = client.app.state.testing_session_local
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def seeded_krx_stock(db_session: Session) -> None:
    db_session.add(
        KrxStock(
            code="005930",
            name="삼성전자",
            name_initials="ㅅㅅㅈㅈ",
            updated_at=seoul_now(),
        )
    )
    db_session.commit()


@pytest.fixture(autouse=True)
def seeded_us_stocks(db_session: Session) -> None:
    db_session.add_all(
        [
            UsStock(code="AAPL", name="Apple Inc", market="NASDAQ", updated_at=seoul_now()),
            UsStock(code="MSFT", name="Microsoft Corporation", market="NASDAQ", updated_at=seoul_now()),
            UsStock(code="F", name="Ford Motor Company", market="NYSE", updated_at=seoul_now()),
        ]
    )
    db_session.commit()


def test_get_ticker_returns_krx_stock_by_code(
    client: TestClient,
    seeded_krx_stock: None,
) -> None:
    response = client.get("/api/tickers/005930")

    assert response.status_code == 200
    assert response.json() == {"code": "005930", "name": "삼성전자", "market": "KR"}


def test_get_ticker_returns_404_when_code_is_unknown(
    client: TestClient,
    seeded_krx_stock: None,
) -> None:
    response = client.get("/api/tickers/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ticker not found"


def test_get_ticker_returns_us_stock_by_code(
    client: TestClient,
    seeded_krx_stock: None,
) -> None:
    response = client.get("/api/tickers/AAPL")

    assert response.status_code == 200
    assert response.json() == {"code": "AAPL", "name": "Apple Inc", "market": "US"}


def test_search_tickers_keeps_korean_name_search(
    client: TestClient,
    seeded_krx_stock: None,
) -> None:
    response = client.get("/api/tickers/search", params={"q": "삼성"})

    assert response.status_code == 200
    assert response.json()[0] == {"code": "005930", "name": "삼성전자", "market": "KR"}


def test_search_tickers_prioritizes_exact_name_match(
    client: TestClient,
    db_session: Session,
    seeded_krx_stock: None,
) -> None:
    db_session.add_all(
        [
            KrxStock(
                code="373220",
                name="LG에너지솔루션",
                name_initials="ㅇㄴㅈㅅㄹㅅ",
                updated_at=seoul_now(),
            ),
            KrxStock(
                code="003550",
                name="LG",
                name_initials="",
                updated_at=seoul_now(),
            ),
            KrxStock(
                code="066570",
                name="LG전자",
                name_initials="ㅈㅈ",
                updated_at=seoul_now(),
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/tickers/search", params={"q": "LG"})

    assert response.status_code == 200
    assert response.json()[0] == {"code": "003550", "name": "LG", "market": "KR"}


def test_search_tickers_returns_us_stock_by_symbol(
    client: TestClient,
    seeded_krx_stock: None,
) -> None:
    response = client.get("/api/tickers/search", params={"q": "AAP"})

    assert response.status_code == 200
    assert response.json() == [{"code": "AAPL", "name": "Apple Inc", "market": "US"}]


def test_search_tickers_returns_us_stock_by_company_name(
    client: TestClient,
    seeded_krx_stock: None,
) -> None:
    response = client.get("/api/tickers/search", params={"q": "Apple"})

    assert response.status_code == 200
    assert response.json() == [{"code": "AAPL", "name": "Apple Inc", "market": "US"}]


def test_search_tickers_supports_single_letter_us_ticker(
    client: TestClient,
    seeded_krx_stock: None,
) -> None:
    response = client.get("/api/tickers/search", params={"q": "F"})

    assert response.status_code == 200
    assert response.json()[0] == {"code": "F", "name": "Ford Motor Company", "market": "US"}


def test_search_tickers_keeps_us_results_visible_for_english_query(
    client: TestClient,
    db_session: Session,
    seeded_krx_stock: None,
) -> None:
    db_session.add_all(
        [
            KrxStock(code="100001", name="A Alpha", name_initials="", updated_at=seoul_now()),
            KrxStock(code="100002", name="A Beta", name_initials="", updated_at=seoul_now()),
            KrxStock(code="100003", name="A Gamma", name_initials="", updated_at=seoul_now()),
            KrxStock(code="100004", name="A Delta", name_initials="", updated_at=seoul_now()),
        ]
    )
    db_session.commit()

    response = client.get("/api/tickers/search", params={"q": "A"})

    assert response.status_code == 200
    assert {"code": "AAPL", "name": "Apple Inc", "market": "US"} in response.json()
