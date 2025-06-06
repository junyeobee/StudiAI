from fastapi.testclient import TestClient
from unittest.mock import patch


def test_notion_webhook_endpoint(client: TestClient):
    with patch('app.api.v1.endpoints.notion_webhook.webhook_handler.process_webhook_event') as mock_proc:
        mock_proc.return_value = None
        response = client.post("/notion_webhook_public/")
        assert response.status_code != 404

