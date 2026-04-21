from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app


def test_app_registers_expected_routes() -> None:
    paths = {route.path for route in app.routes}

    assert "/api/runs" in paths
    assert "/api/runs/{run_id}" in paths
    assert "/api/runs/{run_id}/analyses" in paths
    assert "/api/analyses" in paths
    assert "/api/analyses/{analysis_id}" in paths
    assert "/api/analyses/{analysis_id}/history" in paths


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
