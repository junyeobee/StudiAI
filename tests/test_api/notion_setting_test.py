from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

def test_notion_setting_endpoints_exist(client: TestClient, auth_headers):
    paths = [
        "/notion_setting/workspaces",
        "/notion_setting/workspaces/active",
        "/notion_setting/top-pages",
        "/notion_setting/set-top-page/page1",
        "/notion_setting/get-top-page",
    ]
    for path in paths:
        if path.endswith("/active"):
            response = client.post(path, json={"workspace_id": "ws", "status": "active"}, headers=auth_headers)
        else:
            response = client.get(path, headers=auth_headers)
        assert response.status_code != 404, f"Path failed: {path}"

