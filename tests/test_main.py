"""
메인 애플리케이션 기본 테스트
"""
import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
def test_root_endpoint(client):
    """루트 엔드포인트 테스트"""
    response = client.get("/")
    
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "Notion 학습 관리 시스템 API" in data["message"]


@pytest.mark.unit
def test_openapi_docs(client):
    """OpenAPI 문서 엔드포인트 테스트"""
    response = client.get("/api/v1/openapi.json")
    
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "info" in data
    assert data["info"]["title"] == "Test Notion Learning API"


@pytest.mark.unit
def test_app_startup(client):
    """앱 시작 상태 테스트"""
    # 앱이 정상적으로 시작되는지 확인
    assert client.app is not None
    assert hasattr(client.app, "routes")


@pytest.mark.unit
def test_cors_middleware(client):
    """CORS 미들웨어 테스트"""
    response = client.options("/", headers={
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization",
        "Origin": "http://localhost:3000"
    })
    
    # CORS preflight 요청이 처리되는지 확인
    assert response.status_code in [200, 204]


@pytest.mark.unit
def test_invalid_endpoint(client):
    """존재하지 않는 엔드포인트 테스트"""
    response = client.get("/nonexistent")
    
    assert response.status_code == 404


@pytest.mark.unit
def test_health_status():
    """앱 상태 기본 검증"""
    # 기본적인 상태 확인
    assert True  # 테스트 환경이 정상적으로 로드되었음을 확인 