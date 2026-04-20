from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.crud import create_analysis, create_run
from backend.database import Base
from backend.routers.runs import get_db, router
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


def test_create_run_returns_201_with_run_fields(client: TestClient) -> None:
    response = client.post("/api/runs", json={"memo": "first run"})

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["memo"] == "first run"
    assert body["analysis_count"] == 0
    assert body["created_at"]


def test_list_runs_returns_runs_with_analysis_counts(client: TestClient) -> None:
    create_response = client.post("/api/runs", json={"memo": "second run"})
    second_run_id = create_response.json()["id"]

    app = client.app
    override = app.dependency_overrides[get_db]
    db = next(override())
    try:
        first_run = create_run(db, memo="first run")
        first_run_id = first_run.id
        create_analysis(
            db,
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
    finally:
        db.close()

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
