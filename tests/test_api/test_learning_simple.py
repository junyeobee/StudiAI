"""
간단한 Learning API 엔드포인트 테스트
복잡한 모킹 없이 기본 동작 확인
"""
import pytest


def test_learning_api_structure():
    """learning API 구조가 올바르게 설정되어 있는지 확인"""
    
    # API 라우터 임포트 테스트
    from app.api.v1.endpoints import learning
    
    # 라우터 객체 존재 확인
    assert hasattr(learning, 'router'), "learning 모듈에 router가 없습니다"
    
    # 라우터 타입 확인
    from fastapi import APIRouter
    assert isinstance(learning.router, APIRouter), "learning.router가 APIRouter 타입이 아닙니다"


def test_learning_models_import():
    """학습 관련 모델들이 제대로 임포트되는지 확인"""
    
    try:
        from app.models.learning import (
            LearningPagesRequest,
            PageUpdateRequest
        )
        # 모든 모델이 정상적으로 임포트됨
        assert True
    except ImportError as e:
        pytest.fail(f"학습 모델 임포트 실패: {e}")


def test_learning_services_import():
    """학습 관련 서비스들이 제대로 임포트되는지 확인"""
    
    try:
        from app.services.notion_service import NotionService
        from app.services.supa import (
            insert_learning_page,
            get_used_notion_db_id,
            get_ai_block_id_by_page_id,
            delete_learning_page,
            list_all_learning_databases,
            get_default_workspace
        )
        # 모든 서비스가 정상적으로 임포트됨
        assert True
    except ImportError as e:
        pytest.fail(f"학습 서비스 임포트 실패: {e}")


def test_learning_utils_import():
    """학습 관련 유틸리티들이 제대로 임포트되는지 확인"""
    
    try:
        from app.utils.notion_utils import (
            block_content,
            serialize_page_props
        )
        # 모든 유틸리티가 정상적으로 임포트됨
        assert True
    except ImportError as e:
        pytest.fail(f"학습 유틸리티 임포트 실패: {e}")


def test_workspace_cache_service_import():
    """워크스페이스 캐시 서비스 임포트 확인"""
    
    try:
        from app.services.workspace_cache_service import workspace_cache_service
        assert True
    except ImportError as e:
        pytest.fail(f"워크스페이스 캐시 서비스 임포트 실패: {e}")


def test_learning_api_integration_with_main_app():
    """learning API가 메인 앱에 제대로 통합되었는지 확인"""
    
    # API 라우터 등록 확인
    from app.api.v1.api import api_router
    
    # 라우터의 routes 확인
    routes = [route for route in api_router.routes]
    learning_routes = [route for route in routes if hasattr(route, 'path_regex') and 'learning' in str(route.path_regex)]
    
    # learning 관련 라우트가 존재하는지 확인
    assert len(learning_routes) > 0, "learning 라우트가 메인 API 라우터에 등록되지 않았습니다"


def test_learning_router_has_endpoints():
    """learning 라우터에 엔드포인트들이 등록되어 있는지 확인"""
    
    from app.api.v1.endpoints.learning import router
    
    # 라우터에 등록된 경로들 확인
    routes = router.routes
    assert len(routes) > 0, "learning 라우터에 등록된 엔드포인트가 없습니다"
    
    # 예상되는 엔드포인트 패턴들 확인
    route_paths = [route.path for route in routes if hasattr(route, 'path')]
    
    expected_patterns = ['/pages', '/pages/create', '/pages/{page_id}']
    found_patterns = []
    
    for pattern in expected_patterns:
        for path in route_paths:
            if pattern.replace('{page_id}', '') in path or pattern == path:
                found_patterns.append(pattern)
                break
    
    assert len(found_patterns) > 0, f"예상된 엔드포인트 패턴을 찾을 수 없습니다. 등록된 경로: {route_paths}"


def test_learning_router_methods():
    """learning 라우터의 HTTP 메서드들 확인"""
    
    from app.api.v1.endpoints.learning import router
    
    # 등록된 메서드들 확인
    methods = []
    for route in router.routes:
        if hasattr(route, 'methods'):
            methods.extend(route.methods)
    
    # 필요한 HTTP 메서드들이 등록되어 있는지 확인
    expected_methods = ['GET', 'POST', 'PATCH', 'DELETE']
    for method in expected_methods:
        assert method in methods, f"HTTP 메서드 {method}가 learning 라우터에 등록되지 않았습니다"


def test_learning_dependencies_import():
    """learning 엔드포인트의 의존성들이 제대로 임포트되는지 확인"""
    
    try:
        from app.api.v1.dependencies.auth import require_user
        from app.api.v1.dependencies.workspace import get_user_workspace, get_user_workspace_with_fallback
        from app.api.v1.dependencies.notion import get_notion_service
        from app.core.supabase_connect import get_supabase
        from app.core.redis_connect import get_redis
        assert True
    except ImportError as e:
        pytest.fail(f"learning 의존성 임포트 실패: {e}")


def test_learning_redis_service_import():
    """Redis 서비스 관련 임포트 확인"""
    
    try:
        from app.services.redis_service import RedisService
        redis_service = RedisService()
        assert redis_service is not None
    except ImportError as e:
        pytest.fail(f"Redis 서비스 임포트 실패: {e}")


def test_learning_modules_complete_structure():
    """learning 모듈의 전체 구조가 완전한지 확인"""
    
    # 핵심 모듈들이 모두 임포트 가능한지 확인
    modules_to_test = [
        'app.api.v1.endpoints.learning',
        'app.models.learning',
        'app.services.notion_service',
        'app.services.workspace_cache_service',
        'app.utils.notion_utils'
    ]
    
    for module_name in modules_to_test:
        try:
            __import__(module_name)
        except ImportError as e:
            pytest.fail(f"핵심 learning 모듈 {module_name} 임포트 실패: {e}") 