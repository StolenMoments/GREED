from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.crud import create_analysis, create_run
from backend.database import Base, get_db
from backend.routers.runs import router
from backend.schemas import AnalysisCreate


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
    app.include_router(router)

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


def test_create_run_returns_201_with_run_fields(client: TestClient) -> None:
    response = client.post("/api/runs", json={"memo": "first run"})

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["memo"] == "first run"
    assert body["analysis_count"] == 0
    assert body["created_at"]


def test_create_run_without_memo_returns_201(client: TestClient) -> None:
    response = client.post("/api/runs", json={})

    assert response.status_code == 201
    assert response.json()["memo"] is None


def test_list_runs_empty_returns_empty_list(client: TestClient) -> None:
    response = client.get("/api/runs")

    assert response.status_code == 200
    assert response.json() == []


def test_list_runs_returns_runs_with_analysis_counts(
    client: TestClient, db_session: Session
) -> None:
    second_run_id = client.post("/api/runs", json={"memo": "second run"}).json()["id"]

    first_run = create_run(db_session, memo="first run")
    first_run_id = first_run.id
    create_analysis(
        db_session,
        AnalysisCreate(
            run_id=first_run.id,
            ticker="005930",
            name="Samsung Electronics",
            model="gpt-5.4",
            markdown="analysis",
            judgment="매수",
            trend="상승",
            cloud_position="구름 위",
            ma_alignment="정배열",
        ),
    )

    response = client.get("/api/runs")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert [item["id"] for item in body] == [first_run_id, second_run_id]
    counts = {item["id"]: item["analysis_count"] for item in body}
    assert counts[first_run_id] == 1
    assert counts[second_run_id] == 0


def test_get_run_returns_404_when_missing(client: TestClient) -> None:
    response = client.get("/api/runs/999")

    assert response.status_code == 404
    assert response.json() == {"detail": "Run not found"}


def test_get_run_with_invalid_id_type_returns_422(client: TestClient) -> None:
    response = client.get("/api/runs/not-a-number")

    assert response.status_code == 422
