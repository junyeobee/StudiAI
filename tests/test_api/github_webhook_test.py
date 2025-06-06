import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch


def test_github_webhook_endpoints_exist(client: TestClient, auth_headers):
    with patch('app.api.v1.endpoints.github_webhook.GitHubWebhookService') as mock_service:
        mock_instance = mock_service.return_value
        mock_instance.create_webhook.return_value = {"id": "1"}
        mock_instance.list_repositories.return_value = []

        response = client.post(
            "/github_webhook/",
            json={"repo_url": "https://github.com/test/repo", "learning_db_id": "db1", "events": ["push"]},
            headers=auth_headers,
        )
        assert response.status_code != 404

        response = client.get("/github_webhook/repos", headers=auth_headers)
        assert response.status_code != 404


def test_github_webhook_public_endpoint(client: TestClient):
    with patch('app.api.v1.endpoints.github_webhook.GitHubWebhookHandler') as mock_handler:
        handler_instance = mock_handler.return_value
        handler_instance.handle_webhook.return_value = {"status": "ok"}
        response = client.post("/github_webhook_public/webhook_operation")
        assert response.status_code != 404

