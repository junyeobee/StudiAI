import redis.asyncio as redis
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

async def get_redis(request: Request) -> redis.Redis:
    """의존성 주입을 위한 Redis 클라이언트 제공자"""
    return request.app.state.redis