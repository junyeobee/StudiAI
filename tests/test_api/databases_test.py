"""
데이터베이스 API 엔드포인트 테스트
기본적인 엔드포인트 존재 여부와 구조 확인
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock


@patch('app.api.v1.endpoints.databases.workspace_cache_service.get_workspace_learning_data')
def test_databases_endpoints_exist(mock_cache, client: TestClient, auth_headers):
    """데이터베이스 엔드포인트들이 존재하는지 확인"""
    
    # 활성화된 DB가 있는 경우로 모킹
    mock_cache.return_value = {
        "databases": [
            {
                "db_id": "test_db_123",
                "title": "테스트 DB",
                "status": "used",  # 활성화된 상태
                "parent_page_id": "parent_123",
                "last_used_date": "2024-01-01T00:00:00Z",
                "webhook_id": None,
                "webhook_status": "inactive",
                "workspace_id": "test_workspace"
            }
        ],
        "pages": [],
        "entity_map": {}
    }

    # 엔드포인트 존재 여부 테스트 (404가 아닌 응답 받는지 확인)
    endpoints = [
        "/databases/active",
        "/databases/available",
        "/databases/",
        "/databases/test_id",
        "/databases/deactivate"
    ]

    for endpoint in endpoints:
        with patch('app.api.v1.endpoints.databases.redis_service.set_default_db') as mock_redis:
            mock_redis.return_value = None
            
            if endpoint == "/databases/deactivate":
                with patch('app.api.v1.endpoints.databases.update_learning_database_status') as mock_update:
                    mock_update.return_value = True
                    response = client.post(endpoint, headers=auth_headers)
            elif endpoint == "/databases/test_id":
                response = client.get(endpoint, headers=auth_headers)
            else:
                response = client.get(endpoint, headers=auth_headers)

            # 404가 아니면 엔드포인트가 존재함 (500, 403 등은 가능)
            assert response.status_code != 404, f"엔드포인트 {endpoint}가 존재하지 않습니다"


@patch('app.api.v1.endpoints.databases.redis_service.get_default_page')
@patch('app.api.v1.endpoints.databases.insert_learning_database')
@patch('app.api.v1.endpoints.databases.workspace_cache_service.invalidate_workspace_cache')
def test_databases_post_endpoints_exist(mock_invalidate, mock_insert, mock_get_page, client: TestClient, auth_headers):
    """POST 엔드포인트들 존재 여부 확인"""
    
    # 필요한 함수들 모킹
    mock_get_page.return_value = "mock_parent_page_123"
    mock_insert.return_value = True
    mock_invalidate.return_value = None

    # 데이터베이스 생성 (POST)
    create_data = {"title": "테스트 DB"}
    response = client.post("/databases/", json=create_data, headers=auth_headers)
    # 404가 아니면 엔드포인트 존재 (데이터 검증 실패, 권한 등은 가능)
    assert response.status_code != 404, "데이터베이스 생성 엔드포인트가 존재하지 않습니다"


def test_databases_put_endpoints_exist(client: TestClient, auth_headers):
    """PUT 엔드포인트 존재 여부 확인"""
    
    # 데이터베이스 수정 (PUT)
    update_data = {"title": "수정된 제목"}
    response = client.put("/databases/test_id", json=update_data, headers=auth_headers)
    assert response.status_code != 404, "데이터베이스 수정 엔드포인트가 존재하지 않습니다"


def test_page_databases_endpoint_exists(client: TestClient, auth_headers):
    """페이지 내 데이터베이스 목록 엔드포인트 존재 확인"""
    
    response = client.get("/databases/pages/test_page_id/databases", headers=auth_headers)
    assert response.status_code != 404, "페이지 내 데이터베이스 목록 엔드포인트가 존재하지 않습니다"


def test_databases_api_structure():
    """databases API 구조가 올바르게 설정되어 있는지 확인"""
    
    # API 라우터 임포트 테스트
    from app.api.v1.endpoints import databases
    
    # 라우터 객체 존재 확인
    assert hasattr(databases, 'router'), "databases 모듈에 router가 없습니다"
    
    # 라우터 타입 확인
    from fastapi import APIRouter
    assert isinstance(databases.router, APIRouter), "databases.router가 APIRouter 타입이 아닙니다"


def test_databases_models_import():
    """데이터베이스 관련 모델들이 제대로 임포트되는지 확인"""
    
    try:
        from app.models.database import (
            DatabaseInfo,
            DatabaseCreate,
            DatabaseUpdate,
            DatabaseResponse,
            DatabaseStatus,
            DatabaseMetadata
        )
        # 모든 모델이 정상적으로 임포트됨
        assert True
    except ImportError as e:
        pytest.fail(f"데이터베이스 모델 임포트 실패: {e}")


def test_databases_services_import():
    """데이터베이스 관련 서비스들이 제대로 임포트되는지 확인"""
    
    try:
        from app.services.notion_service import NotionService
        from app.services.supa import (
            list_all_learning_databases,
            update_learning_database_status,
            get_active_learning_database,
            insert_learning_database,
            get_db_info_by_id,
            update_learning_database
        )
        # 모든 서비스가 정상적으로 임포트됨
        assert True
    except ImportError as e:
        pytest.fail(f"데이터베이스 서비스 임포트 실패: {e}")


def test_auth_headers_format(auth_headers):
    """인증 헤더 형식이 올바른지 확인"""
    
    assert "Authorization" in auth_headers
    assert auth_headers["Authorization"].startswith("Bearer ")
    assert len(auth_headers["Authorization"]) > len("Bearer ")


def test_client_basic_functionality(client: TestClient):
    """테스트 클라이언트 기본 기능 확인"""
    
    # 루트 엔드포인트 테스트 (인증 불필요)
    response = client.get("/")
    assert response.status_code == 200
    
    # OpenAPI 문서 확인 (인증 불필요) - 정확한 경로 사용
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200 