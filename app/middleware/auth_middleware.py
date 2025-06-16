"""
인증 미들웨어
사용자 인증 정보를 request.state에 설정하여 전역 예외 핸들러에서 사용할 수 있도록 함
"""
from fastapi import Request, HTTPException
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.services.auth_service import verify_api_key
from app.core.redis_connect import get_redis
from app.services.redis_service import RedisService
from app.utils.logger import api_logger
import redis

redis_service = RedisService()


class AuthMiddleware(BaseHTTPMiddleware):
    """
    인증 미들웨어
    - Authorization 헤더에서 사용자 ID 추출
    - request.state.user_id에 설정
    - 공개 엔드포인트는 건너뛰기
    """
    
    def __init__(self, app, supabase_client=None):
        super().__init__(app)
        self.supabase_client = supabase_client
        
        # 인증이 필요 없는 공개 엔드포인트들
        self.public_paths = {
            "/",
            "/health", 
            "/docs",
            "/redoc",
            "/openapi.json"
        }
        
        # prefix로 시작하는 공개 경로들
        self.public_prefixes = {
            "/auth_public",  # 공개 인증 엔드포인트들
            "/docs",         # FastAPI 문서
            "/redoc"         # ReDoc 문서
        }
    
    async def dispatch(self, request: Request, call_next):
        """요청 처리 전에 사용자 인증 정보 설정"""
        
        # 1. 공개 엔드포인트 확인
        if self._is_public_path(request.url.path):
            api_logger.debug(f"공개 엔드포인트 요청: {request.url.path}")
            return await call_next(request)
        
        # 2. Authorization 헤더 확인
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            # 인증 헤더가 없어도 일단 진행 (의존성에서 처리)
            return await call_next(request)
        
        # 3. API 키 추출 및 사용자 ID 획득
        try:
            api_key = auth_header.split(" ")[1]
            user_id = await self._get_user_id(api_key, request)
            
            if user_id:
                # request.state에 사용자 정보 설정
                request.state.user_id = user_id
                api_logger.debug(f"사용자 인증 성공: {user_id}")
            else:
                api_logger.debug("유효하지 않은 API 키")
                
        except Exception as e:
            api_logger.warning(f"인증 처리 중 오류: {str(e)}")
            # 오류가 발생해도 요청은 계속 진행 (의존성에서 최종 판단)
        
        # 4. 다음 미들웨어/핸들러로 요청 전달
        return await call_next(request)
    
    def _is_public_path(self, path: str) -> bool:
        """공개 엔드포인트인지 확인"""
        # 정확한 매치
        if path in self.public_paths:
            return True
        
        # prefix 매치
        for prefix in self.public_prefixes:
            if path.startswith(prefix):
                return True
                
        return False
    
    async def _get_user_id(self, api_key: str, request: Request) -> str | None:
        """API 키로 사용자 ID 조회 (Redis 캐시 활용)"""
        try:
            # Redis 클라이언트 초기화
            redis_client = await get_redis(request)
            
            # 1. Redis에서 먼저 조회
            user_id = await redis_service.get_user_id(api_key, redis_client)
            if user_id:
                return user_id
            
            # 2. Redis에 없으면 Supabase에서 조회
            if self.supabase_client:
                user_id = await verify_api_key(api_key, self.supabase_client)
                if user_id:
                    # Redis에 캐시 저장 (10분 만료)
                    try:
                        await redis_service.set_user_id(user_id, api_key, redis_client)
                    except Exception as cache_error:
                        api_logger.warning(f"Redis 캐시 저장 실패: {str(cache_error)}")
                    return user_id
            
            return None
            
        except Exception as e:
            api_logger.error(f"사용자 ID 조회 실패: {str(e)}")
            return None 