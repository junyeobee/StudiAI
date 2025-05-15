import redis.asyncio as redis
from app.utils.retry import async_retry
from app.utils.logger import api_logger
from app.core.exceptions import RedisError

class RedisService:
    def __init__(self):
        self.logger = api_logger
    
    @async_retry(max_retries=3)
    async def set_token(self, user_id: str, token: str, redis_client: redis.Redis, expire_seconds: int = 3600) -> bool:
        """
        토큰을 Redis에 저장 (기본 1시간 만료)
        """
        try:
            self.logger.info(f"사용자 토큰 저장 시작: {user_id}")
            result = redis_client.set(f"user:{user_id}:token", token, ex=expire_seconds)
            self.logger.info(f"사용자 토큰 저장 완료: {user_id}")
            return result
        except Exception as e:
            self.logger.error(f"사용자 토큰 저장 실패: {str(e)}")
            raise RedisError(f"토큰 저장 실패: {str(e)}")

    @async_retry(max_retries=3)
    async def get_token(self, user_id: str, redis_client: redis.Redis) -> str:
        """
        토큰을 Redis에서 가져옴
        """
        try:
            self.logger.info(f"사용자 토큰 조회 시작: {user_id}")
            result = redis_client.get(f"user:{user_id}:token")
            self.logger.info(f"사용자 토큰 조회 완료: {user_id}")
            return result
        except Exception as e:
            self.logger.error(f"사용자 토큰 조회 실패: {str(e)}")
            raise RedisError(f"토큰 조회 실패: {str(e)}")
    
    async def get_user_workspace(self, user_id: str, redis_client: redis.Redis) -> str:
        """
        사용자 워크스페이스 정보를 Redis에서 가져옴
        """
        return redis_client.get(f"user:{user_id}:workspace")
    
    async def set_user_workspace(self, user_id: str, workspace: str, redis_client: redis.Redis) -> bool:
        """
        사용자 워크스페이스 정보를 Redis에 저장
        """
        return redis_client.set(f"user:{user_id}:workspace", workspace)
