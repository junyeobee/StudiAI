import redis
from app.utils.retry import async_retry
from app.utils.logger import api_logger
from app.core.exceptions import RedisError
import json
import uuid

class RedisService:
    def __init__(self):
        self.logger = api_logger
    async def set_user_id(self, user_id:str, bearer_token: str, redis_client: redis.Redis) -> bool:
        """
        Bearer 토큰을 통해 사용자 ID를 저장(1시간 만료)
        """
        try:
            return redis_client.set(f"user:{bearer_token}:id", user_id, ex = 3600)
        except Exception as e:
            self.logger.warning(f"Redis 오류 발생: {str(e)}")
            return False
    
    async def get_user_id(self, bearer_token: str, redis_client: redis.Redis) -> str:
        """
        Bearer 토큰을 통해 사용자 ID를 조회
        """
        try:
            # Redis 조회 시도
            user_id = redis_client.get(f"user:{bearer_token}:id")
            if user_id:
                return user_id
        except (redis.ConnectionError, redis.TimeoutError) as e:
            self.logger.warning(f"Redis 연결 실패: {str(e)}")
        except Exception as e:
            self.logger.warning(f"Redis 오류 발생: {str(e)}")
        return None
    
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
        try: 
            return redis_client.get(f"user:{user_id}:workspace")
        except Exception as e:
            self.logger.error(f"사용자 워크스페이스 조회 실패: {str(e)}")
            raise RedisError(f"워크스페이스 조회 실패: {str(e)}")
    
    async def set_user_workspace(self, user_id: str, workspace: str, redis_client: redis.Redis) -> bool:
        """
        사용자 워크스페이스 정보를 Redis에 저장
        """
        try: 
            return redis_client.set(f"user:{user_id}:workspace", workspace)
        except Exception as e:
            self.logger.error(f"사용자 워크스페이스 저장 실패: {str(e)}")
            raise RedisError(f"워크스페이스 저장 실패: {str(e)}")
    
    async def get_workspace_pages(self, workspace_id: str, redis_client: redis.Redis) -> list:
        """
        워크스페이스 페이지 정보를 Redis에서 가져옴
        """
        try: 
            data = redis_client.get(f"workspace:{workspace_id}:pages")
            if data:
                # JSON 문자열을 리스트로 변환
                return json.loads(data)
            return None
        except Exception as e:
            self.logger.error(f"워크스페이스 페이지 조회 실패: {str(e)}")
            raise RedisError(f"워크스페이스 페이지 조회 실패: {str(e)}")
    
    async def set_workspace_pages(self, workspace_id: str, pages: list, redis_client: redis.Redis) -> bool:
        """
        워크스페이스 페이지 정보를 Redis에 저장
        """
        # 리스트를 JSON 문자열로 변환
        json_data = json.dumps(pages)
        try: 
            return redis_client.set(f"workspace:{workspace_id}:pages", json_data)
        except Exception as e:
            self.logger.error(f"워크스페이스 페이지 저장 실패: {str(e)}")
            raise RedisError(f"워크스페이스 페이지 저장 실패: {str(e)}")
    
    async def set_default_page(self, workspace_id: str, page_id: str, redis_client: redis.Redis) -> bool:
        """
        워크스페이스의 기본 페이지 설정
        """
        try: 
            return redis_client.set(f"workspace:{workspace_id}:default_page", page_id)
        except Exception as e:
            self.logger.error(f"워크스페이스 기본 페이지 설정 실패: {str(e)}")
            raise RedisError(f"워크스페이스 기본 페이지 설정 실패: {str(e)}")

    async def get_default_page(self, workspace_id: str, redis_client: redis.Redis) -> str:
        """
        워크스페이스의 기본 페이지 가져오기
        """
        try: 
            return redis_client.get(f"workspace:{workspace_id}:default_page")
        except Exception as e:
            self.logger.error(f"워크스페이스 기본 페이지 조회 실패: {str(e)}")
            raise RedisError(f"워크스페이스 기본 페이지 조회 실패: {str(e)}")
    
    async def set_state_uuid(self, user_id: str, redis_client: redis.Redis, expire_seconds: int = 180) -> str:
        """
        OAuth 인증용 state UUID를 생성하고 Redis에 저장 (3분 만료)
        """
        state_uuid = str(uuid.uuid4())
        key = f"auth:state:{user_id}"
        print(key)
        print(state_uuid)
        redis_client.set(key, state_uuid, ex=expire_seconds)
        return state_uuid

    async def validate_state_uuid(self, user_id: str, uuid_to_check: str, redis_client: redis.Redis) -> bool:
        """
        OAuth 콜백에서 state UUID 검증
        """
        key = f"auth:state:{user_id}"
        stored_uuid = redis_client.get(key)
        
        # 값이 일치하면 삭제하고 True 반환
        if stored_uuid == uuid_to_check:
            redis_client.delete(key)
            return True
        
        return False
        
