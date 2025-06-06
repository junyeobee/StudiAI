"""
Databases API 엔드포인트 HTTP 호출 테스트
conftest.py의 공통 NotionService 모킹 사용
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.notion_service import NotionService


def test_databases_active_endpoint_http(client: TestClient, auth_headers):
    """활성화된 데이터베이스 조회 엔드포인트 - HTTP 호출"""
    
    # workspace_cache_service 함수 직접 모킹
    with patch('app.api.v1.endpoints.databases.workspace_cache_service.get_workspace_learning_data') as mock_cache:
        mock_cache.return_value = {
            "databases": [
                {
                    "db_id": "test_db_123",
                    "title": "테스트 학습 DB",
                    "status": "used",  # 활성화된 상태
                    "parent_page_id": "parent_123"
                }
            ]
        }
        
        # redis_service.set_default_db 모킹
        with patch('app.api.v1.endpoints.databases.redis_service.set_default_db') as mock_redis:
            mock_redis.return_value = None
            
            response = client.get("/databases/active", headers=auth_headers)
            
            # 404가 아니면 엔드포인트 존재
            assert response.status_code != 404, "활성화된 데이터베이스 조회 엔드포인트가 존재하지 않습니다"


def test_databases_available_endpoint_http(client: TestClient, auth_headers):
    """사용 가능한 데이터베이스 목록 조회 엔드포인트 - HTTP 호출"""
    
    with patch('app.api.v1.endpoints.databases.workspace_cache_service.get_workspace_learning_data') as mock_cache:
        mock_cache.return_value = {
            "databases": [
                {
                    "db_id": "db_1",
                    "title": "학습 계획",
                    "status": "used",
                    "parent_page_id": "parent_1"
                },
                {
                    "db_id": "db_2", 
                    "title": "프로젝트 관리",
                    "status": "ready",
                    "parent_page_id": "parent_2"
                }
            ]
        }
        
        response = client.get("/databases/available", headers=auth_headers)
        
        assert response.status_code != 404, "사용 가능한 데이터베이스 목록 조회 엔드포인트가 존재하지 않습니다"


def test_databases_list_endpoint_http(client: TestClient, auth_headers):
    """데이터베이스 목록 조회 엔드포인트 - HTTP 호출"""
    
    with patch('app.api.v1.endpoints.databases.workspace_cache_service.get_workspace_learning_data') as mock_cache:
        mock_cache.return_value = {
            "databases": [
                {
                    "db_id": "db_1",
                    "title": "학습 DB 1",
                    "status": "used",
                    "parent_page_id": "parent_1",
                    "last_used_date": "2024-01-01T00:00:00Z",
                    "webhook_id": None,
                    "webhook_status": "inactive",
                    "workspace_id": "test_workspace"
                },
                {
                    "db_id": "db_2", 
                    "title": "학습 DB 2",
                    "status": "ready",
                    "parent_page_id": "parent_2",
                    "last_used_date": "2024-01-01T00:00:00Z",
                    "webhook_id": None,
                    "webhook_status": "inactive",
                    "workspace_id": "test_workspace"
                }
            ]
        }
        
        response = client.get("/databases/", headers=auth_headers)
        
        assert response.status_code != 404, "데이터베이스 목록 조회 엔드포인트가 존재하지 않습니다"


def test_databases_create_endpoint_http(client: TestClient, auth_headers):
    """데이터베이스 생성 엔드포인트 - HTTP 호출"""
    
    # 필요한 함수들 모킹 (conftest.py의 NotionService 모킹 사용)
    with patch('app.api.v1.endpoints.databases.redis_service.get_default_page') as mock_get_page, \
         patch('app.api.v1.endpoints.databases.insert_learning_database') as mock_insert, \
         patch('app.api.v1.endpoints.databases.workspace_cache_service.invalidate_workspace_cache') as mock_invalidate:
        
        # 기본 페이지 설정
        mock_get_page.return_value = "parent_page_123"
        mock_insert.return_value = True
        mock_invalidate.return_value = None
        
        create_data = {
            "title": "테스트 데이터베이스",
            "description": "테스트용 설명"
        }
        
        response = client.post("/databases/", json=create_data, headers=auth_headers)
        
        assert response.status_code != 404, "데이터베이스 생성 엔드포인트가 존재하지 않습니다"


def test_databases_get_by_id_endpoint_http(client: TestClient, auth_headers):
    """특정 데이터베이스 조회 엔드포인트 - HTTP 호출 (conftest.py 모킹 사용)"""
    
    response = client.get("/databases/test_db_123", headers=auth_headers)
    
    assert response.status_code != 404, "특정 데이터베이스 조회 엔드포인트가 존재하지 않습니다"


def test_databases_activate_endpoint_http(client: TestClient, auth_headers):
    """데이터베이스 활성화 엔드포인트 - HTTP 호출"""
    
    # 필요한 함수들 모킹
    with patch('app.api.v1.endpoints.databases.update_learning_database_status') as mock_update, \
         patch('app.api.v1.endpoints.databases.workspace_cache_service.invalidate_workspace_cache') as mock_invalidate:
        
        mock_update.return_value = True
        mock_invalidate.return_value = None
        
        response = client.post("/databases/test_db_123/activate", headers=auth_headers)
        
        assert response.status_code != 404, "데이터베이스 활성화 엔드포인트가 존재하지 않습니다"


def test_databases_deactivate_endpoint_http(client: TestClient, auth_headers):
    """데이터베이스 비활성화 엔드포인트 - HTTP 호출"""
    
    with patch('app.api.v1.endpoints.databases.update_learning_database_status') as mock_update, \
         patch('app.api.v1.endpoints.databases.workspace_cache_service.invalidate_workspace_cache') as mock_invalidate:
        
        mock_update.return_value = True
        mock_invalidate.return_value = None
        
        response = client.post("/databases/deactivate", headers=auth_headers)
        
        assert response.status_code != 404, "데이터베이스 비활성화 엔드포인트가 존재하지 않습니다"


def test_databases_page_databases_endpoint_http(client: TestClient, auth_headers):
    """페이지의 하위 데이터베이스 조회 엔드포인트 - HTTP 호출 (conftest.py 모킹 사용)"""
    
    response = client.get("/databases/pages/test_page_123/databases", headers=auth_headers)
    
    assert response.status_code != 404, "페이지 하위 데이터베이스 조회 엔드포인트가 존재하지 않습니다"


def test_databases_comprehensive_http_methods(client: TestClient, auth_headers):
    """데이터베이스 엔드포인트의 다양한 HTTP 메서드 테스트"""
    
    # 공통 모킹 설정
    with patch('app.api.v1.endpoints.databases.workspace_cache_service.get_workspace_learning_data') as mock_cache, \
         patch('app.api.v1.endpoints.databases.update_learning_database_status') as mock_update:
        
        mock_cache.return_value = {
            "databases": [
                {
                    "db_id": "test", 
                    "title": "Test",
                    "status": "used",
                    "parent_page_id": "parent_test",
                    "last_used_date": "2024-01-01T00:00:00Z",
                    "webhook_id": None,
                    "webhook_status": "inactive",
                    "workspace_id": "test_workspace"
                }
            ]
        }
        mock_update.return_value = True
        
        # GET 메서드들만 테스트 (POST는 복잡한 의존성 때문에 제외)
        test_cases = [
            ("GET", "/databases/", None),
            ("GET", "/databases/available", None),  
        ]
        
        for method, endpoint, data in test_cases:
            response = client.get(endpoint, headers=auth_headers)
            
            # 모든 엔드포인트가 404가 아닌 응답 반환
            assert response.status_code != 404, f"{method} {endpoint} 엔드포인트가 존재하지 않습니다" 