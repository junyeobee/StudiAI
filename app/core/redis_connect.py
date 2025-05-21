import redis
import redis.asyncio
from fastapi import Request
from app.core.config import settings

async def init_redis_client() -> redis.Redis:
    try:
        client = redis.Redis(
            host=(settings.REDIS_HOST),
            port=int(settings.REDIS_PORT),
            password=(settings.REDIS_PASSWORD),
            decode_responses=True,
            username="default",
        )
        return client
    except Exception as e:
        raise e
    
async def init_redis_async_client() -> redis.asyncio.Redis:
    """비동기 Redis 클라이언트 초기화"""
    try:
        client = redis.asyncio.Redis(
            host=(settings.REDIS_HOST),
            port=int(settings.REDIS_PORT),
            password=(settings.REDIS_PASSWORD),
            decode_responses=True,
            username="default",
        )
        # 연결 테스트
        await client.ping()
        return client
    except Exception as e:
        raise e

async def get_redis(request: Request) -> redis.Redis:
    """의존성 주입을 위한 Redis 클라이언트 제공자"""
    return request.app.state.redis

async def get_redis_async(request: Request) -> redis.asyncio.Redis:
    """비동기 의존성 주입을 위한 Redis 클라이언트 제공자"""
    return request.app.state.redis_async
