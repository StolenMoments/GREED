from __future__ import annotations

from collections.abc import Generator
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend import crud
from backend.database import Base, get_db
from backend.routers import stock


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    app = FastAPI()
    app.include_router(stock.router)

    def override_get_db() -> Generator[Session, None, None]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db_session(client: TestClient) -> Generator[Session, None, None]:
    override = client.app.dependency_overrides[get_db]
    session = next(override())
    try:
        yield session
    finally:
        session.close()


def test_refresh_stock_price_fetches_even_when_today_cache_exists(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crud.upsert_stock_price(
        db_session,
        ticker="005930",
        price_date=date.today(),
        close_price=70000,
    )
    calls: list[str] = []

    def fake_fetch_latest_close(ticker: str) -> tuple[date, float]:
        calls.append(ticker)
        return date.today() + timedelta(days=1), 71500.0

    monkeypatch.setattr(stock, "fetch_latest_close", fake_fetch_latest_close)

    response = client.post("/api/stock/005930/price/refresh")

    assert response.status_code == 200
    body = response.json()
    assert calls == ["005930"]
    assert body["ticker"] == "005930"
    assert body["close_price"] == 71500.0
    assert body["price_date"] == (date.today() + timedelta(days=1)).isoformat()

    cached = crud.get_stock_price(db_session, "005930")
    assert cached is not None
    assert cached.close_price == 71500.0


def test_refresh_stock_price_returns_404_when_fetch_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stock, "fetch_latest_close", lambda ticker: None)

    response = client.post("/api/stock/005930/price/refresh")

    assert response.status_code == 404
    assert response.json()["detail"] == "가격 데이터를 가져올 수 없습니다."
