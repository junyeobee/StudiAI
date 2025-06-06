import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch


def test_auth_endpoints_exist(client: TestClient, auth_headers):
    endpoints = [
        ("POST", "/auth_public/keys", {"user_id": "test"}),
        ("GET", "/auth/keys?user_id=test", None),
        ("DELETE", "/auth/keys/key123?user_id=test", None),
    ]

    for method, url, data in endpoints:
        if method == "POST":
            response = client.post(url, json=data, headers=auth_headers)
        elif method == "DELETE":
            response = client.delete(url, headers=auth_headers)
        else:
            response = client.get(url, headers=auth_headers)
        assert response.status_code != 404


@pytest.mark.asyncio
async def test_oauth_callback(client: TestClient):
    with patch('app.api.v1.endpoints.auth.parse_oauth_state') as mock_parse, \
         patch('app.api.v1.endpoints.auth.process_notion_oauth') as mock_proc, \
         patch('app.api.v1.endpoints.auth.redis_service.validate_state_uuid') as mock_validate:
        mock_parse.return_value = ("test_user_12345", "uuid")
        mock_validate.return_value = True
        mock_proc.return_value = {"access_token": "token"}
        response = client.get("/auth_public/callback/notion?code=123&state=x")
        assert response.status_code != 404

