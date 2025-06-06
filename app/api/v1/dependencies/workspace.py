"""
워크스페이스 관련 FastAPI 의존성
"""
from fastapi import HTTPException, Depends
from app.api.v1.dependencies.auth import require_user
from app.core.redis_connect import get_redis
from app.core.supabase_connect import get_supabase
from app.services.redis_service import RedisService
from app.services.supa import get_default_workspace
from supabase._async.client import AsyncClient
import redis

redis_service = RedisService()

async def get_user_workspace(
    user_id: str = Depends(require_user),
    redis_client: redis.Redis = Depends(get_redis)
) -> str:
    """
    사용자의 워크스페이스 ID 조회 (필수)
    Redis에서만 조회하며, 없으면 에러 발생
    """
    workspace_id = await redis_service.get_user_workspace(user_id, redis_client)

    if not workspace_id:
        raise HTTPException(
            status_code=404, 
            detail="기본 워크스페이스를 설정해주세요."
        )
    return workspace_id

async def get_user_workspace_with_fallback(
    user_id: str = Depends(require_user),
    redis_client: redis.Redis = Depends(get_redis),
    supabase: AsyncClient = Depends(get_supabase)
) -> str:
    """
    사용자의 워크스페이스 ID 조회 (Redis → Supabase fallback)
    둘 다 없으면 에러 발생
    """
    # Redis에서 먼저 조회
    workspace_id = await redis_service.get_user_workspace(user_id, redis_client)
    
    if not workspace_id:
        # Supabase에서 fallback 조회
        workspace_id = await get_default_workspace(user_id, supabase)
        
        if not workspace_id:
            raise HTTPException(
                status_code=404, 
                detail="활성 워크스페이스를 찾을 수 없습니다."
            )
    
    return workspace_id 