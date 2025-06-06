from fastapi.testclient import TestClient


def test_worker_endpoints_exist(client: TestClient):
    paths = [
        "/worker/health",
        "/worker/queue/stats",
        "/worker/queue/details",
        "/worker/monitor",
    ]
    for path in paths:
        response = client.get(path)
        assert response.status_code != 404

