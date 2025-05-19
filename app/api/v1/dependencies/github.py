from fastapi import Depends, HTTPException
from app.core.redis_connect import get_redis
from app.services.redis_service import RedisService
from app.core.supabase_connect import get_supabase
from supabase._async.client import AsyncClient
from app.services.github_webhook_service import GitHubWebhookService
from app.api.v1.dependencies.auth import require_user
from app.utils.logger import api_logger
import redis
from app.services.auth_service import get_integration_token

redis_service = RedisService()

async def get_github_webhook_service(
    user_id: str = Depends(require_user), 
    supabase: AsyncClient = Depends(get_supabase),
    redis: redis.Redis = Depends(get_redis)
):
    # Redis 서비스 초기화
    try:
        # 먼저 Redis에서 토큰 조회 시도
        try:
            token = await redis_service.get_token(user_id, redis)
        except Exception as e:
            pass
        
        # Redis에 토큰이 없으면 Supabase에서 조회 후 Redis에 저장
        if token is None:
            api_logger.info(f"Redis에 토큰 없음, Supabase에서 조회: {user_id}")
            token = await get_integration_token(user_id=user_id, provider="github", supabase=supabase)
            # 조회한 토큰을 Redis에 저장 (1시간 만료)
            if token:
                try:
                    await redis_service.set_token(user_id, token, redis, expire_seconds=3600)
                except Exception as e:
                    pass
        else:
            api_logger.info(f"Redis에서 토큰 조회 성공: {user_id}")
            
    except Exception as e:
        api_logger.error(f"Github 토큰 조회 실패: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Github 통합 정보가 없습니다."
        )
        
    return GitHubWebhookService(token=token)