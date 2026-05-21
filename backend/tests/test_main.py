from __future__ import annotations

import logging

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from backend.database import get_db
from backend.main import UvicornAccessLogFilter, app


def test_app_registers_expected_routes() -> None:
    paths = {route.path for route in app.routes}

    assert "/api/runs" in paths
    assert "/api/runs/{run_id}" in paths
    assert "/api/runs/{run_id}/analyses" in paths
    assert "/api/analyses" in paths
    assert "/api/analyses/{analysis_id}" in paths
    assert "/api/analyses/{analysis_id}/history" in paths
    analysis_detail_methods: set[str] = set()
    for route in app.routes:
        if route.path == "/api/analyses/{analysis_id}":
            analysis_detail_methods.update(getattr(route, "methods", set()))
    assert "DELETE" in analysis_detail_methods
    assert "/api/stock/{ticker}/price" in paths
    assert "/api/stock/{ticker}/price/refresh" in paths
    assert "/api/tickers/{code}" in paths
    assert "/api/jobs/trigger-analysis" in paths
    assert "/api/jobs/{job_id}" in paths


def test_cors_allows_localhost_5173() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/api/runs",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_uvicorn_access_log_filter_suppresses_success_statuses() -> None:
    access_filter = UvicornAccessLogFilter()

    for status_code in (200, 201, 202, 204):
        record = logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname=__file__,
            lineno=0,
            msg='%s - "%s %s HTTP/%s" %d',
            args=("127.0.0.1:12345", "GET", "/api/health", "1.1", status_code),
            exc_info=None,
        )

        assert access_filter.filter(record) is False


def test_uvicorn_access_log_filter_keeps_non_success_statuses() -> None:
    access_filter = UvicornAccessLogFilter()

    for status_code in (302, 400, 404, 422, 500):
        record = logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname=__file__,
            lineno=0,
            msg='%s - "%s %s HTTP/%s" %d',
            args=("127.0.0.1:12345", "GET", "/api/health", "1.1", status_code),
            exc_info=None,
        )

        assert access_filter.filter(record) is True


def test_health_reports_database_up(monkeypatch) -> None:
    monkeypatch.setattr("backend.main.init_db", lambda: None)
    monkeypatch.setattr(
        "backend.main.get_database_health",
        lambda: {"status": "up", "checked_at": "2026-05-15T12:00:00+09:00"},
    )

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "api": "ok",
        "database": {"status": "up", "checked_at": "2026-05-15T12:00:00+09:00"},
    }


def test_app_starts_when_database_init_fails(monkeypatch) -> None:
    def fail_init() -> None:
        raise OperationalError("SELECT 1", {}, Exception("tunnel down"))

    monkeypatch.setattr("backend.main.init_db", fail_init)
    monkeypatch.setattr(
        "backend.main.get_database_health",
        lambda: {"status": "down", "checked_at": "2026-05-15T12:00:00+09:00"},
    )

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["database"]["status"] == "down"


def test_database_errors_return_service_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("backend.main.init_db", lambda: None)

    def failing_get_db():
        raise OperationalError("SELECT 1", {}, Exception("tunnel down"))
        yield

    app.dependency_overrides[get_db] = failing_get_db
    try:
        with TestClient(app) as client:
            response = client.get("/api/runs")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "데이터베이스 연결이 끊겼습니다. 터널을 확인하고 잠시 후 다시 시도하세요.",
        "code": "database_unavailable",
    }
