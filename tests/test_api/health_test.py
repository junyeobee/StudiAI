import pytest
from fastapi.testclient import TestClient


def test_health_endpoints_exist(client: TestClient):
    paths = [
        "/health/healthz",
        "/health/health/ready",
        "/health/health/detailed",
        "/health/health/metrics",
    ]
    for path in paths:
        response = client.get(path)
        assert response.status_code != 404

    response = client.post("/health/health/cleanup")
    assert response.status_code != 404

