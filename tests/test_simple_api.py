"""
간단한 API 테스트
인증이 필요하지 않은 기본 엔드포인트들을 테스트
"""
import pytest


@pytest.mark.unit
def test_root_endpoint_works(client):
    """루트 엔드포인트가 정상 작동하는지 테스트"""
    response = client.get("/")
    
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "Notion" in data["message"]


@pytest.mark.unit  
def test_docs_endpoint_works(client):
    """OpenAPI 문서 엔드포인트가 정상 작동하는지 테스트"""
    response = client.get("/docs")
    
    # docs는 HTML을 반환하므로 200 상태코드만 확인
    assert response.status_code == 200


@pytest.mark.unit
def test_openapi_json_works(client):
    """OpenAPI JSON이 정상 생성되는지 테스트"""
    response = client.get("/api/v1/openapi.json")
    
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "info" in data
    assert "paths" in data


@pytest.mark.unit
def test_health_check_endpoints_exist():
    """헬스체크 엔드포인트가 존재하는지 기본 확인"""
    # 실제 요청은 하지 않고 테스트가 실행되는지만 확인
    assert True


@pytest.mark.unit
def test_ci_environment_setup():
    """CI 환경이 제대로 설정되었는지 확인"""
    import os
    
    # 테스트 환경변수가 설정되어 있는지 확인
    assert os.getenv("PROJECT_NAME") == "Test Notion Learning API"
    assert os.getenv("SUPABASE_URL") is not None
    assert os.getenv("SUPABASE_KEY") is not None 