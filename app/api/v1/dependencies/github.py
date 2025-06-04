from fastapi import Depends, HTTPException
from app.core.redis_connect import get_redis
from app.services.redis_service import RedisService
from app.core.supabase_connect import get_supabase
from supabase._async.client import AsyncClient
from app.services.github_webhook_service import GitHubWebhookService
from app.api.v1.dependencies.auth import require_user
from app.utils.logger import api_logger
import redis.asyncio as redis
from app.services.auth_service import get_integration_token

redis_service = RedisService()

async def get_github_webhook_service(
    user_id: str = Depends(require_user), 
    supabase: AsyncClient = Depends(get_supabase),
    redis: redis.Redis = Depends(get_redis)
):
    """깃허브 웹훅 서비스 객체 생성 - 연동이 안 되어 있으면 예외 발생"""
    try:
        # 먼저 Redis에서 토큰 조회 시도
        token = await redis_service.get_token(user_id, "github", redis)
        
        # Redis에 토큰이 없으면 Supabase에서 조회 후 Redis에 저장
        if token is None:
            api_logger.info(f"Redis에 토큰 없음, Supabase에서 조회: {user_id}")
            token = await get_integration_token(user_id=user_id, provider="github", supabase=supabase)
            
            if not token:
                raise HTTPException(
                    status_code=400,
                    detail="깃허브 연동을 먼저 진행해주세요."
                )
            
            # 조회한 토큰을 Redis에 저장 (1시간 만료)
            await redis_service.set_token(user_id, token, "github", redis, expire_seconds=3600)
        else:
            api_logger.info(f"Redis에서 토큰 조회 성공: {user_id}")
            
    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(f"깃허브 토큰 조회 실패: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="깃허브 연동 상태 확인 중 오류가 발생했습니다."
        )
        
    return GitHubWebhookService(token=token)