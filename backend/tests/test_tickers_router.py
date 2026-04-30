from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.models import KrxStock
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


def test_get_ticker_returns_krx_stock_by_code(
    client: TestClient,
    seeded_krx_stock: None,
) -> None:
    response = client.get("/api/tickers/005930")

    assert response.status_code == 200
    assert response.json() == {"code": "005930", "name": "삼성전자"}


def test_get_ticker_returns_404_when_code_is_unknown(
    client: TestClient,
    seeded_krx_stock: None,
) -> None:
    response = client.get("/api/tickers/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ticker not found"


def test_get_ticker_rejects_non_krx_code(
    client: TestClient,
    seeded_krx_stock: None,
) -> None:
    response = client.get("/api/tickers/AAPL")

    assert response.status_code == 400
    assert response.json()["detail"] == "6-digit Korean ticker required"


def test_search_tickers_keeps_korean_name_search(
    client: TestClient,
    seeded_krx_stock: None,
) -> None:
    response = client.get("/api/tickers/search", params={"q": "삼성"})

    assert response.status_code == 200
    assert response.json() == [{"code": "005930", "name": "삼성전자"}]
