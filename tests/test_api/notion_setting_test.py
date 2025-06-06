from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock


@patch('app.services.supa.get_workspaces')
@patch('app.services.supa.switch_active_workspace')
@patch('app.api.v1.endpoints.notion_setting.redis_service.get_workspace_pages')
@patch('app.api.v1.endpoints.notion_setting.redis_service.set_workspace_pages')
@patch('app.api.v1.endpoints.notion_setting.redis_service.set_default_page')
@patch('app.api.v1.endpoints.notion_setting.redis_service.get_default_page')
def test_notion_setting_endpoints_exist(
    mock_get_page, mock_set_page, mock_set_pages, mock_get_pages, 
    mock_switch, mock_get_workspaces, client: TestClient, auth_headers
):
    # 필요한 함수들 모킹
    mock_get_workspaces.return_value = [
        {"workspace_id": "test_workspace", "workspace_name": "Test Workspace", "is_active": True}
    ]
    mock_switch.return_value = True
    mock_get_pages.return_value = [
        {"page_id": "page1", "title": "Page 1"},
        {"page_id": "page2", "title": "Page 2"}
    ]
    mock_set_pages.return_value = True
    mock_set_page.return_value = True
    mock_get_page.return_value = "default_page_123"
    
    paths = [
        "/notion_setting/workspaces",
        "/notion_setting/workspaces/active",
        "/notion_setting/top-pages",
        "/notion_setting/set-top-page?page_id=123",
        "/notion_setting/get-top-page",
    ]
    for path in paths:
        if path.endswith("/active"):
            response = client.post(path, json={"workspace_id": "ws", "status": "active"}, headers=auth_headers)
        elif "set-top-page" in path:
            response = client.get(path, headers=auth_headers)
        else:
            response = client.get(path, headers=auth_headers)
        assert response.status_code != 404

