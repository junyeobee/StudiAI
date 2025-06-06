"""
pytest 설정 및 공통 픽스처
CI 테스트를 위한 공통 설정들
"""
import asyncio
import os
import sys
import pytest
from fastapi.testclient import TestClient
from typing import Generator, AsyncGenerator
from unittest.mock import Mock, AsyncMock

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 테스트 환경변수 설정 (메인 앱 임포트 전에 설정)
os.environ.update({
    "PROJECT_NAME": "Test Notion Learning API",
    "SUPABASE_URL": "https://test-project.supabase.co",
    "SUPABASE_KEY": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test", 
    "NOTION_CLIENT_ID": "test_client_id",
    "NOTION_CLIENT_SECRET": "test_client_secret",
    "NOTION_WEBHOOK_SECRET": "test_webhook_secret",
    "WEBHOOK_CREATE_URL": "test_create_url",
    "WEBHOOK_DELETE_URL": "test_delete_url",
    "REDIS_HOST": "localhost",
    "REDIS_PORT": "6379",
    "REDIS_PASSWORD": "test_password",
    "GITHUB_CLIENT_ID": "test_github_id",
    "GITHUB_SECRET_KEY": "test_github_secret",
    "SECRET_KEY": "test_secret_key_for_testing_purposes_only",
    "ENCRYPTION_KEY": "test_encryption_key_32_characters!",
    "WEBHOOK_SECRET_KEY": "test_webhook_secret_key",
    "API_BASE_URL": "http://testserver",
    "LOG_LEVEL": "DEBUG"
})

from fastapi import FastAPI
from app.core.config import settings
from app.api.v1.api import api_router, public_router
from app.api.v1.dependencies.auth import require_user
from app.core.exception_handlers import register_exception_handlers
from app.core.supabase_connect import get_supabase
from app.core.redis_connect import get_redis
from app.services.auth_service import verify_api_key


# 테스트용 앱 생성
def create_test_app() -> FastAPI:
    """테스트용 FastAPI 앱 생성 (lifespan 이벤트 없이)"""
    test_app = FastAPI(
        title=settings.PROJECT_NAME,
        description=settings.PROJECT_DESCRIPTION,
        version=settings.APP_VERSION,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        debug=False
    )
    
    # CORS 설정
    from fastapi.middleware.cors import CORSMiddleware
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 전역 예외 핸들러 등록
    register_exception_handlers(test_app)
    
    # API 라우터 등록
    from fastapi import Depends
    test_app.include_router(api_router, dependencies=[Depends(require_user)])
    test_app.include_router(public_router)
    
    @test_app.get("/")
    async def root():
        """루트 엔드포인트"""
        return {"message": "Notion 학습 관리 시스템 API"}
    
    return test_app


# 비동기 테스트 설정
@pytest.fixture(scope="session")
def event_loop():
    """세션 범위의 이벤트 루프 생성"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def app(mock_supabase, mock_redis, test_user_id):
    """테스트용 FastAPI 앱"""
    test_app = create_test_app()
    
    # 테스트용 state 설정
    test_app.state.supabase = mock_supabase
    test_app.state.redis = mock_redis
    
    # 인증 의존성 오버라이드 - require_user를 직접 모킹
    def mock_require_user():
        return test_user_id
    
    # 워크스페이스 의존성도 모킹
    def mock_get_user_workspace():
        return "test_workspace"
    
    # NotionService 의존성을 더 정교하게 모킹
    def mock_get_notion_service():
        """정교한 NotionService 모킹 - 실제 데이터 반환"""
        mock_service = Mock()  # AsyncMock 대신 Mock 사용
        
        # get_active_database 모킹
        async def mock_get_active_database(db_info):
            return {
                "db_id": db_info.get("db_id", "mock_db_123"),
                "title": db_info.get("title", "Mock Database"),
                "status": "active"
            }
        
        # get_database 모킹 - DatabaseInfo 호환 형태로 반환
        async def mock_get_database(db_id, workspace_id):
            return {
                "db_id": db_id,
                "title": f"Database {db_id}",
                "parent_page_id": "mock_parent_123",
                "status": "ready",
                "last_used_date": "2024-01-01T00:00:00Z",
                "webhook_id": None,
                "webhook_status": "inactive",
                "workspace_id": workspace_id
            }
        
        # create_database 모킹 - DatabaseInfo 객체 반환
        async def mock_create_database(title, parent_page_id):
            # DatabaseInfo 모델 임포트
            from app.models.database import DatabaseInfo, DatabaseStatus
            
            return DatabaseInfo(
                db_id="new_mock_db_123",
                title=title,
                parent_page_id=parent_page_id,
                status=DatabaseStatus.READY,
                webhook_id=None,
                webhook_status=None,
                last_used_date=None,
                workspace_id="test_workspace"
            )
        
        # list_databases_in_page 모킹 - DatabaseMetadata 형식으로 반환
        async def mock_list_databases_in_page(page_id, workspace_id):
            return [
                {
                    "id": f"child_db_1_{page_id}",  # 'db_id'가 아닌 'id' 필드 사용
                    "title": "Child Database 1"
                },
                {
                    "id": f"child_db_2_{page_id}",  # 'db_id'가 아닌 'id' 필드 사용
                    "title": "Child Database 2"
                }
            ]
        
        # update_database 모킹
        async def mock_update_database(db_id, db_update):
            class MockUpdateResult:
                def __init__(self):
                    self.db_id = db_id
                    self.title = f"Updated {db_id}"
                    self.parent_page_id = "updated_parent_123"
            
            return MockUpdateResult()
        
        # 모킹된 메서드들을 서비스에 할당
        mock_service.get_active_database = mock_get_active_database
        mock_service.get_database = mock_get_database
        mock_service.create_database = mock_create_database
        mock_service.list_databases_in_page = mock_list_databases_in_page
        mock_service.update_database = mock_update_database
        
        return mock_service
    
    # 의존성 오버라이드 적용
    test_app.dependency_overrides[require_user] = mock_require_user
    test_app.dependency_overrides[get_supabase] = lambda: mock_supabase  
    test_app.dependency_overrides[get_redis] = lambda: mock_redis
    
    from app.api.v1.dependencies.workspace import get_user_workspace
    from app.api.v1.dependencies.notion import get_notion_service
    test_app.dependency_overrides[get_user_workspace] = mock_get_user_workspace
    test_app.dependency_overrides[get_notion_service] = mock_get_notion_service
    
    return test_app


@pytest.fixture
def client(app) -> Generator[TestClient, None, None]:
    """FastAPI 테스트 클라이언트"""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_supabase():
    """모킹된 Supabase 클라이언트"""
    mock_client = AsyncMock()
    
    # 체이닝 메서드를 위한 mock 객체들 설정
    mock_table = AsyncMock()
    mock_select = AsyncMock()
    mock_insert = AsyncMock()
    mock_update = AsyncMock()
    mock_delete = AsyncMock()
    mock_eq = AsyncMock()
    mock_execute = AsyncMock()
    
    # 기본 응답 데이터 설정
    mock_response = AsyncMock()
    mock_response.data = []
    mock_response.count = 0
    
    # 체이닝 구조 설정
    mock_execute.return_value = mock_response
    
    mock_eq.return_value.execute = mock_execute
    mock_select.return_value.eq = mock_eq
    mock_select.return_value.execute = mock_execute
    
    mock_insert.return_value.execute = mock_execute
    mock_update.return_value.execute = mock_execute  
    mock_delete.return_value.execute = mock_execute
    
    mock_table.select = mock_select
    mock_table.insert = mock_insert
    mock_table.update = mock_update
    mock_table.delete = mock_delete
    
    mock_client.table.return_value = mock_table
    
    return mock_client


@pytest.fixture
def mock_redis():
    """모킹된 Redis 클라이언트"""
    mock_redis = Mock()
    mock_redis.get.return_value = None
    mock_redis.set.return_value = True
    mock_redis.delete.return_value = True
    mock_redis.exists.return_value = False
    return mock_redis


@pytest.fixture
def test_user_id():
    """테스트용 사용자 ID"""
    return "test_user_12345"


@pytest.fixture
def test_api_key():
    """테스트용 API 키"""
    return "test_api_key_abcdef123456"


@pytest.fixture
def auth_headers(test_api_key):
    """인증 헤더"""
    return {"Authorization": f"Bearer {test_api_key}"}


@pytest.fixture
async def mock_auth_dependencies(app, mock_supabase, mock_redis, test_user_id):
    """인증 의존성 모킹"""
    
    # Supabase 의존성 오버라이드
    def get_mock_supabase():
        return mock_supabase
    
    def get_mock_redis():
        return mock_redis
    
    app.dependency_overrides[get_supabase] = get_mock_supabase
    app.dependency_overrides[get_redis] = get_mock_redis
    
    # verify_api_key 함수 모킹
    original_verify = verify_api_key
    
    async def mock_verify_api_key(api_key: str, supabase):
        if api_key == "test_api_key_abcdef123456":
            return test_user_id
        return None
    
    # 모킹 적용
    import app.services.auth_service
    app.services.auth_service.verify_api_key = mock_verify_api_key
    
    yield
    
    # 의존성 오버라이드 정리
    app.dependency_overrides.clear()
    
    # 원본 함수 복원
    app.services.auth_service.verify_api_key = original_verify


@pytest.fixture
def authenticated_client(client, auth_headers, mock_auth_dependencies):
    """인증된 테스트 클라이언트"""
    return client, auth_headers


@pytest.fixture
def sample_database_data():
    """테스트용 데이터베이스 샘플 데이터"""
    return {
        "database_id": "test_db_12345",
        "database_name": "Test Database",
        "user_id": "test_user_12345",
        "notion_token": "test_notion_token",
        "webhook_id": "test_webhook_12345",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
    }


@pytest.fixture
def sample_page_data():
    """테스트용 페이지 샘플 데이터"""
    return {
        "page_id": "test_page_12345",
        "database_id": "test_db_12345", 
        "page_title": "Test Page",
        "ai_summary_block_id": "test_block_12345",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z"
    }


@pytest.fixture
def sample_webhook_data():
    """테스트용 웹훅 샘플 데이터"""
    return {
        "webhook_id": "test_webhook_12345",
        "database_id": "test_db_12345",
        "webhook_url": "https://test.webhook.url",
        "is_active": True,
        "created_at": "2024-01-01T00:00:00Z"
    }


@pytest.fixture(autouse=True)
async def setup_test_environment():
    """각 테스트 전에 실행되는 환경 설정"""
    # 테스트 전 설정
    yield
    # 테스트 후 정리 (필요시)
    pass


# pytest 마커 정의
def pytest_configure(config):
    """pytest 설정"""
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests") 