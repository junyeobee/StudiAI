from fastapi import Depends, HTTPException, Request
from supabase._async.client import AsyncClient
from app.services.auth_service import verify_api_key
from app.core.supabase_connect import get_supabase
from app.core.redis_connect import get_redis
from app.services.redis_service import RedisService
import redis

redis_service = RedisService()

async def require_user(request: Request, supabase: AsyncClient = Depends(get_supabase), redis: redis.Redis = Depends(get_redis)) -> str:
    """API 키를 통한 사용자 인증 및 식별"""
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증 토큰 없음")
    api_key = auth_header.split(" ")[1]
    try:
        user_id = await redis_service.get_user_id(api_key, redis)
        if user_id:
            return user_id
    except Exception as e:
        pass
    try:
        res = await verify_api_key(api_key, supabase)
        if not res:
            raise HTTPException(status_code=403, detail="유효하지 않은 토큰")
        try: 
            await redis_service.set_user_id(res, api_key, redis)
        except Exception as e:
            pass
        return res
    except Exception as e:
        raise HTTPException(status_code=403, detail=f"토큰 검증 실패: {str(e)}")
    
    