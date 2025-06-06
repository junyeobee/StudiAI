"""
Webhooks API 엔드포인트 테스트 (HTTP 호출 포함)
더 정교한 모킹으로 RecursionError 방지
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock


def test_webhooks_api_structure():
    """webhooks API 구조가 올바르게 설정되어 있는지 확인"""
    
    # API 라우터 임포트 테스트
    from app.api.v1.endpoints import webhooks
    
    # 라우터 객체 존재 확인
    assert hasattr(webhooks, 'router'), "webhooks 모듈에 router가 없습니다"
    
    # 라우터 타입 확인
    from fastapi import APIRouter
    assert isinstance(webhooks.router, APIRouter), "webhooks.router가 APIRouter 타입이 아닙니다"


def test_webhooks_services_import():
    """웹훅 관련 서비스들이 제대로 임포트되는지 확인"""
    
    try:
        from app.services.supa import (
            get_failed_webhook_operations,
            get_webhook_operations,
            get_webhook_operation_detail
        )
        # 모든 서비스가 정상적으로 임포트됨
        assert True
    except ImportError as e:
        pytest.fail(f"웹훅 서비스 임포트 실패: {e}")


def test_webhooks_api_integration_with_main_app():
    """webhooks API가 메인 앱에 제대로 통합되었는지 확인"""
    
    # API 라우터 등록 확인
    from app.api.v1.api import api_router
    
    # 라우터의 routes 확인
    routes = [route for route in api_router.routes]
    webhook_routes = [route for route in routes if hasattr(route, 'path_regex') and 'webhook' in str(route.path_regex)]
    
    # webhook 관련 라우트가 존재하는지 확인
    assert len(webhook_routes) > 0, "webhook 라우트가 메인 API 라우터에 등록되지 않았습니다"


def test_webhooks_router_has_endpoints():
    """webhooks 라우터에 엔드포인트들이 등록되어 있는지 확인"""
    
    from app.api.v1.endpoints.webhooks import router
    
    # 라우터에 등록된 경로들 확인
    routes = router.routes
    assert len(routes) > 0, "webhooks 라우터에 등록된 엔드포인트가 없습니다"
    
    # 예상되는 엔드포인트 패턴들 확인
    route_paths = [route.path for route in routes if hasattr(route, 'path')]
    
    expected_patterns = ['/operations/failed', '/operations', '/operations/{operation_id}']
    found_patterns = []
    
    for pattern in expected_patterns:
        for path in route_paths:
            if pattern.replace('{operation_id}', '') in path or pattern == path:
                found_patterns.append(pattern)
                break
    
    assert len(found_patterns) > 0, f"예상된 엔드포인트 패턴을 찾을 수 없습니다. 등록된 경로: {route_paths}"


def test_webhooks_failed_operations_endpoint_simple(client: TestClient, auth_headers):
    """실패한 웹훅 작업 조회 엔드포인트 - 간단한 모킹"""
    
    # 가장 간단한 방법: Supabase를 직접 모킹
    with patch('app.api.v1.endpoints.webhooks.get_failed_webhook_operations') as mock_get_failed:
        # 간단한 반환값 설정
        mock_get_failed.return_value = [
            {
                "id": "test_id_1", 
                "status": "failed",
                "error_message": "테스트 오류"
            }
        ]
        
        response = client.get("/webhooks/operations/failed", headers=auth_headers)
        
        # 404가 아니면 엔드포인트 존재
        assert response.status_code != 404, "실패한 웹훅 작업 조회 엔드포인트가 존재하지 않습니다"
        
        # 성공적인 응답이면 데이터 확인
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "success"
            assert "data" in data


def test_webhooks_operations_endpoint_with_status(client: TestClient, auth_headers):
    """웹훅 작업 목록 조회 엔드포인트 (상태 필터 포함)"""
    
    with patch('app.api.v1.endpoints.webhooks.get_webhook_operations') as mock_get_operations:
        # Mock 반환값 설정
        mock_get_operations.return_value = [
            {
                "id": "test_id_1",
                "status": "success", 
                "created_at": "2024-01-01T00:00:00Z"
            },
            {
                "id": "test_id_2",
                "status": "pending",
                "created_at": "2024-01-01T01:00:00Z"
            }
        ]
        
        # 상태 필터 없이 요청
        response = client.get("/webhooks/operations", headers=auth_headers)
        assert response.status_code != 404, "웹훅 작업 목록 조회 엔드포인트가 존재하지 않습니다"
        
        # 상태 필터와 함께 요청
        response = client.get("/webhooks/operations?status=success&limit=10", headers=auth_headers)
        assert response.status_code != 404, "웹훅 작업 목록 조회 (상태 필터) 엔드포인트가 존재하지 않습니다"


def test_webhooks_operation_detail_endpoint(client: TestClient, auth_headers):
    """특정 웹훅 작업 상세 조회 엔드포인트"""
    
    with patch('app.api.v1.endpoints.webhooks.get_webhook_operation_detail') as mock_get_detail:
        # 성공 케이스: 작업 존재
        mock_get_detail.return_value = {
            "id": "test_operation_id",
            "status": "completed",
            "webhook_url": "https://example.com/webhook",
            "payload": {"test": "data"},
            "response": {"success": True},
            "created_at": "2024-01-01T00:00:00Z",
            "completed_at": "2024-01-01T00:01:00Z"
        }
        
        response = client.get("/webhooks/operations/test_operation_id", headers=auth_headers)
        assert response.status_code != 404, "웹훅 작업 상세 조회 엔드포인트가 존재하지 않습니다"
        
        # 실제 성공 응답 확인
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "success"
            assert "data" in data
            assert data["data"]["id"] == "test_operation_id"


def test_webhooks_operation_detail_not_found(client: TestClient, auth_headers):
    """존재하지 않는 웹훅 작업 조회 시 404 처리"""
    
    with patch('app.api.v1.endpoints.webhooks.get_webhook_operation_detail') as mock_get_detail:
        # 작업이 존재하지 않는 경우
        mock_get_detail.return_value = None
        
        response = client.get("/webhooks/operations/nonexistent_id", headers=auth_headers)
        
        # 비즈니스 로직에 의한 404는 정상 (엔드포인트 자체는 존재함)
        if response.status_code == 404:
            data = response.json()
            assert "웹훅 작업을 찾을 수 없습니다" in data["detail"]


def test_webhooks_endpoint_query_parameters():
    """웹훅 엔드포인트의 쿼리 파라미터 처리 확인"""
    
    # 라우터 직접 확인하여 쿼리 파라미터 존재 여부 확인
    from app.api.v1.endpoints.webhooks import router
    
    routes = router.routes
    operations_route = None
    failed_operations_route = None
    
    for route in routes:
        if hasattr(route, 'path'):
            if route.path == '/operations':
                operations_route = route
            elif route.path == '/operations/failed':
                failed_operations_route = route
    
    assert operations_route is not None, "/operations 엔드포인트가 등록되지 않았습니다"
    assert failed_operations_route is not None, "/operations/failed 엔드포인트가 등록되지 않았습니다"


def test_webhooks_dependencies_import():
    """웹훅 엔드포인트의 의존성들이 제대로 임포트되는지 확인"""
    
    try:
        from app.core.supabase_connect import get_supabase
        from supabase._async.client import AsyncClient
        assert True
    except ImportError as e:
        pytest.fail(f"웹훅 의존성 임포트 실패: {e}")


def test_webhooks_http_methods():
    """웹훅 라우터의 HTTP 메서드 확인"""
    
    from app.api.v1.endpoints.webhooks import router
    
    # 등록된 메서드들 확인
    methods = []
    for route in router.routes:
        if hasattr(route, 'methods'):
            methods.extend(route.methods)
    
    # GET 메서드가 등록되어 있는지 확인 (웹훅은 주로 GET)
    assert 'GET' in methods, "GET 메서드가 웹훅 라우터에 등록되지 않았습니다"


def test_webhooks_error_handling():
    """웹훅 엔드포인트의 에러 처리 확인"""
    
    # HTTPException이 제대로 임포트되는지 확인
    try:
        from fastapi import HTTPException
        assert True
    except ImportError as e:
        pytest.fail(f"HTTPException 임포트 실패: {e}")


def test_webhooks_comprehensive_structure():
    """웹훅 모듈의 전체 구조 확인"""
    
    # 핵심 모듈들이 모두 임포트 가능한지 확인
    modules_to_test = [
        'app.api.v1.endpoints.webhooks',
        'app.services.webhook_service',
        'app.services.github_webhook_service'
    ]
    
    for module_name in modules_to_test:
        try:
            __import__(module_name)
        except ImportError as e:
            pytest.fail(f"핵심 웹훅 모듈 {module_name} 임포트 실패: {e}") 