"""
Admin 엔드포인트 테스트
/api/v1/admin 경로의 모든 엔드포인트 테스트
"""
import pytest
import os
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


@pytest.mark.api
class TestAdminErrorStatistics:
    """에러 통계 엔드포인트 테스트"""
    
    @pytest.mark.asyncio
    async def test_get_error_statistics_success(self, authenticated_client, mock_supabase):
        """에러 통계 조회 성공 테스트"""
        client, headers = authenticated_client
        
        # mock_supabase 응답 설정
        mock_response = AsyncMock()
        mock_response.data = [
            {
                "version_tag": "v1.0.0",
                "exception_type": "NotionAPIError", 
                "count": 5,
                "latest_error": "2024-01-01T10:00:00Z"
            }
        ]
        mock_supabase.table.return_value.select.return_value.execute.return_value = mock_response
        
        # 에러 통계 서비스 모킹
        with patch('app.api.v1.endpoints.admin.get_error_statistics') as mock_service:
            mock_service.return_value = {
                "total_errors": 10,
                "by_version": [{"version_tag": "v1.0.0", "count": 5}],
                "by_type": [{"exception_type": "NotionAPIError", "count": 5}]
            }
            
            response = client.get("/admin/error-statistics", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "total_errors" in data["data"]
        assert data["message"] == "에러 통계 조회 완료"
    
    @pytest.mark.asyncio
    async def test_get_error_statistics_with_version_filter(self, authenticated_client):
        """버전 필터링 에러 통계 조회 테스트"""
        client, headers = authenticated_client
        
        with patch('app.api.v1.endpoints.admin.get_error_statistics') as mock_service:
            mock_service.return_value = {
                "total_errors": 3,
                "by_version": [{"version_tag": "v1.0.0", "count": 3}]
            }
            
            response = client.get(
                "/admin/error-statistics?version_tag=v1.0.0&limit=50",
                headers=headers
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        # 서비스 호출 인자 확인
        mock_service.assert_called_once()
        call_args = mock_service.call_args
        assert call_args.kwargs["version_tag"] == "v1.0.0"
        assert call_args.kwargs["limit"] == 50
    
    def test_get_error_statistics_unauthorized(self, client):
        """인증 없는 요청 테스트"""
        response = client.get("/admin/error-statistics")
        
        assert response.status_code == 401
        data = response.json()
        assert "인증 토큰 없음" in data["detail"]
    
    @pytest.mark.asyncio
    async def test_get_error_statistics_service_error(self, authenticated_client):
        """에러 통계 서비스 오류 테스트"""
        client, headers = authenticated_client
        
        with patch('app.api.v1.endpoints.admin.get_error_statistics') as mock_service:
            mock_service.side_effect = Exception("Database connection failed")
            
            response = client.get("/admin/error-statistics", headers=headers)
        
        assert response.status_code == 500
        data = response.json()
        assert "에러 통계 조회 중 오류가 발생했습니다" in data["detail"]


@pytest.mark.api
class TestAdminHealthCheck:
    """헬스체크 엔드포인트 테스트"""
    
    @pytest.mark.asyncio
    async def test_error_logging_health_success(self, authenticated_client, mock_supabase):
        """에러 로깅 헬스체크 성공 테스트"""
        client, headers = authenticated_client
        
        # Supabase 쿼리 성공 모킹
        mock_response = AsyncMock()
        mock_response.data = [{"id": "test-id"}]
        mock_supabase.table.return_value.select.return_value.limit.return_value.execute.return_value = mock_response
        
        response = client.get("/admin/health/error-logging", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["error_logging_status"] == "healthy"
        assert data["data"]["supabase_connection"] == "connected"
        assert data["message"] == "에러 로깅 시스템 정상 동작"
    
    @pytest.mark.asyncio
    async def test_error_logging_health_failure(self, authenticated_client, mock_supabase):
        """에러 로깅 헬스체크 실패 테스트"""
        client, headers = authenticated_client
        
        # Supabase 쿼리 실패 모킹
        mock_supabase.table.side_effect = Exception("Connection timeout")
        
        response = client.get("/admin/health/error-logging", headers=headers)
        
        assert response.status_code == 200  # 헬스체크는 실패해도 200 반환
        data = response.json()
        assert data["status"] == "error"
        assert data["data"]["error_logging_status"] == "unhealthy"
        assert data["data"]["supabase_connection"] == "failed"
        assert "Connection timeout" in data["data"]["error_detail"]
    
    def test_error_logging_health_unauthorized(self, client):
        """인증 없는 헬스체크 요청 테스트"""
        response = client.get("/admin/health/error-logging")
        
        assert response.status_code == 401


@pytest.mark.api
class TestAdminTestEndpoints:
    """개발/테스트용 엔드포인트 테스트"""
    
    def test_trigger_test_error_notion_api(self, authenticated_client):
        """Notion API 에러 트리거 테스트"""
        client, headers = authenticated_client
        
        # 개발 환경 설정
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            response = client.post(
                "/admin/test/trigger-error/notion_api",
                headers=headers
            )
        
        assert response.status_code == 500  # 예외 핸들러에 의해 500 반환
        # 실제로 NotionAPIError가 발생했는지는 로그나 예외 핸들러를 통해 확인
    
    def test_trigger_test_error_database(self, authenticated_client):
        """Database 에러 트리거 테스트"""
        client, headers = authenticated_client
        
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            response = client.post(
                "/admin/test/trigger-error/database",
                headers=headers
            )
        
        assert response.status_code == 500
    
    def test_trigger_test_error_webhook(self, authenticated_client):
        """Webhook 에러 트리거 테스트"""
        client, headers = authenticated_client
        
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            response = client.post(
                "/admin/test/trigger-error/webhook", 
                headers=headers
            )
        
        assert response.status_code == 500
    
    def test_trigger_test_error_validation(self, authenticated_client):
        """Validation 에러 트리거 테스트"""
        client, headers = authenticated_client
        
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            response = client.post(
                "admin/test/trigger-error/validation",
                headers=headers
            )
        
        assert response.status_code == 500
    
    def test_trigger_test_error_learning(self, authenticated_client):
        """Learning 에러 트리거 테스트"""
        client, headers = authenticated_client
        
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            response = client.post(
                "/admin/test/trigger-error/learning",
                headers=headers
            )
        
        assert response.status_code == 500
    
    def test_trigger_test_error_redis(self, authenticated_client):
        """Redis 에러 트리거 테스트"""
        client, headers = authenticated_client
        
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            response = client.post(
                "/admin/test/trigger-error/redis",
                headers=headers
            )
        
        assert response.status_code == 500
    
    def test_trigger_test_error_github_api(self, authenticated_client):
        """GitHub API 에러 트리거 테스트"""
        client, headers = authenticated_client
        
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            response = client.post(
                "/admin/test/trigger-error/github_api",
                headers=headers
            )
        
        assert response.status_code == 500
    
    def test_trigger_test_error_generic(self, authenticated_client):
        """일반 예외 트리거 테스트"""
        client, headers = authenticated_client
        
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            response = client.post(
                "/admin/test/trigger-error/generic",
                headers=headers
            )
        
        assert response.status_code == 500
    
    def test_trigger_test_error_invalid_type(self, authenticated_client):
        """지원하지 않는 에러 유형 테스트"""
        client, headers = authenticated_client
        
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            response = client.post(
                "/admin/test/trigger-error/invalid_type",
                headers=headers
            )
        
        assert response.status_code == 400
        data = response.json()
        assert "지원하지 않는 에러 유형" in data["detail"]
    
    def test_trigger_test_error_production_env(self, authenticated_client):
        """운영 환경에서 테스트 에러 트리거 차단 테스트"""
        client, headers = authenticated_client
        
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            response = client.post(
                "/admin/test/trigger-error/notion_api",
                headers=headers
            )
        
        assert response.status_code == 404
        data = response.json()
        assert "개발 환경에서만 사용 가능" in data["detail"]
    
    def test_trigger_test_error_unauthorized(self, client):
        """인증 없는 테스트 에러 트리거 요청"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            response = client.post("/admin/test/trigger-error/notion_api")
        
        assert response.status_code == 401
    
    def test_get_version_info_success(self, authenticated_client):
        """버전 정보 조회 성공 테스트"""
        client, headers = authenticated_client
        
        with patch.dict(os.environ, {
            "ENVIRONMENT": "development",
            "APP_VERSION": "v1.2.3"
        }):
            response = client.get("/admin/test/version-info", headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["app_version"] == "v1.2.3"
        assert data["data"]["environment"] == "development"
        assert data["message"] == "버전 정보 조회 완료"
    
    def test_get_version_info_production_env(self, authenticated_client):
        """운영 환경에서 버전 정보 조회 차단 테스트"""
        client, headers = authenticated_client
        
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            response = client.get("/admin/test/version-info", headers=headers)
        
        assert response.status_code == 404
        data = response.json()
        assert "개발 환경에서만 사용 가능" in data["detail"]
    
    def test_get_version_info_unauthorized(self, client):
        """인증 없는 버전 정보 조회 요청"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            response = client.get("/admin/test/version-info")
        
        assert response.status_code == 401


@pytest.mark.api
class TestAdminIntegration:
    """Admin 엔드포인트 통합 테스트"""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_admin_workflow(self, authenticated_client, mock_supabase):
        """관리자 워크플로우 통합 테스트"""
        client, headers = authenticated_client
        
        # 1. 헬스체크 확인
        mock_response = AsyncMock()
        mock_response.data = [{"id": "test-id"}]
        mock_supabase.table.return_value.select.return_value.limit.return_value.execute.return_value = mock_response
        
        health_response = client.get("/admin/health/error-logging", headers=headers)
        assert health_response.status_code == 200
        assert health_response.json()["data"]["error_logging_status"] == "healthy"
        
        # 2. 에러 통계 조회
        with patch('app.api.v1.endpoints.admin.get_error_statistics') as mock_service:
            mock_service.return_value = {"total_errors": 0}
            
            stats_response = client.get("/admin/error-statistics", headers=headers)
            assert stats_response.status_code == 200
            assert stats_response.json()["status"] == "success"
        
        # 3. 개발 환경에서 버전 정보 확인  
        with patch.dict(os.environ, {"ENVIRONMENT": "development", "APP_VERSION": "test-v1.0.0"}):
            version_response = client.get("/admin/test/version-info", headers=headers)
            assert version_response.status_code == 200
            assert version_response.json()["data"]["app_version"] == "test-v1.0.0" 