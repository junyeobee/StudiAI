import redis
from app.utils.retry import async_retry
from app.utils.logger import api_logger
from app.core.exceptions import RedisError
import json
import uuid

class RedisService:
    def __init__(self):
        self.logger = api_logger
        
    async def set_user_id(self, user_id: str, bearer_token: str, redis_client: redis.Redis) -> bool:
        """
        Bearer 토큰을 통해 사용자 ID를 저장(1시간 만료)
        """
        try:
            result = redis_client.set(f"user:{bearer_token}:id", user_id, ex=3600)
            return bool(result)
        except Exception as e:
            self.logger.error(f"사용자 ID 저장 실패: {str(e)}")
            raise RedisError(f"사용자 ID 저장 실패: {str(e)}")
    
    async def get_user_id(self, bearer_token: str, redis_client: redis.Redis) -> str:
        """
        Bearer 토큰을 통해 사용자 ID를 조회
        """
        try:
            user_id = redis_client.get(f"user:{bearer_token}:id")
            return user_id if user_id else None
        except (redis.ConnectionError, redis.TimeoutError) as e:
            self.logger.warning(f"Redis 연결 실패: {str(e)}")
            raise RedisError(f"Redis 연결 실패: {str(e)}")
        except Exception as e:
            self.logger.error(f"사용자 ID 조회 실패: {str(e)}")
            raise RedisError(f"사용자 ID 조회 실패: {str(e)}")
    
    @async_retry(max_retries=3)
    async def set_token(self, user_id: str, token: str, provider: str, redis_client: redis.Redis, expire_seconds: int = 3600) -> bool:
        """
        토큰을 Redis에 저장 (기본 1시간 만료)
        """
        try:
            self.logger.info(f"사용자 토큰 저장 시작: {user_id}")
            result = redis_client.set(f"user:{user_id}:provider:{provider}", token, ex=expire_seconds)
            self.logger.info(f"사용자 토큰 저장 완료: {user_id}")
            return bool(result)
        except Exception as e:
            self.logger.error(f"사용자 토큰 저장 실패: {str(e)}")
            raise RedisError(f"토큰 저장 실패: {str(e)}")

    @async_retry(max_retries=3)
    async def get_token(self, user_id: str, provider: str, redis_client: redis.Redis) -> str:
        """
        토큰을 Redis에서 가져옴
        """
        try:
            self.logger.info(f"사용자 토큰 조회 시작: {user_id}")
            result = redis_client.get(f"user:{user_id}:provider:{provider}")
            self.logger.info(f"사용자 토큰 조회 완료: {user_id}")
            return result if result else None
        except Exception as e:
            self.logger.error(f"사용자 토큰 조회 실패: {str(e)}")
            raise RedisError(f"토큰 조회 실패: {str(e)}")
    
    async def get_user_workspace(self, user_id: str, redis_client: redis.Redis) -> str:
        """
        사용자 워크스페이스 정보를 Redis에서 가져옴
        """
        try: 
            result = redis_client.get(f"user:{user_id}:workspace")
            return result if result else None
        except Exception as e:
            self.logger.error(f"사용자 워크스페이스 조회 실패: {str(e)}")
            raise RedisError(f"워크스페이스 조회 실패: {str(e)}")
    
    async def set_user_workspace(self, user_id: str, workspace_id: str, redis_client: redis.Redis) -> bool:
        """
        사용자 워크스페이스 정보를 Redis에 저장
        """
        try: 
            result = redis_client.set(f"user:{user_id}:workspace", workspace_id)
            return bool(result)
        except Exception as e:
            self.logger.error(f"사용자 워크스페이스 저장 실패: {str(e)}")
            raise RedisError(f"워크스페이스 저장 실패: {str(e)}")
    
    async def get_workspace_pages(self, user_id: str, workspace_id: str, redis_client: redis.Redis) -> list:
        """
        워크스페이스 페이지 정보를 Redis에서 가져옴
        """
        try: 
            data = redis_client.get(f"user:{user_id}:workspace:{workspace_id}:pages")
            if data:
                # JSON 문자열을 리스트로 변환
                return json.loads(data)
            return None
        except Exception as e:
            self.logger.error(f"워크스페이스 페이지 조회 실패: {str(e)}")
            raise RedisError(f"워크스페이스 페이지 조회 실패: {str(e)}")
    
    async def set_workspace_pages(self, user_id: str, workspace_id: str, pages: list, redis_client: redis.Redis) -> bool:
        """
        워크스페이스 페이지 정보를 Redis에 저장
        """
        try:
            # 리스트를 JSON 문자열로 변환
            json_data = json.dumps(pages)
            result = redis_client.set(f"user:{user_id}:workspace:{workspace_id}:pages", json_data)
            return bool(result)
        except Exception as e:
            self.logger.error(f"워크스페이스 페이지 저장 실패: {str(e)}")
            raise RedisError(f"워크스페이스 페이지 저장 실패: {str(e)}")
    
    async def set_default_page(self, user_id: str, workspace_id: str, page_id: str, redis_client: redis.Redis) -> bool:
        """
        워크스페이스의 기본 페이지 설정
        """
        try: 
            result = redis_client.set(f"user:{user_id}:workspace:{workspace_id}:default_page", page_id)
            return bool(result)
        except Exception as e:
            self.logger.error(f"워크스페이스 기본 페이지 설정 실패: {str(e)}")
            raise RedisError(f"워크스페이스 기본 페이지 설정 실패: {str(e)}")

    async def get_default_page(self, user_id: str, workspace_id: str, redis_client: redis.Redis) -> str:
        """
        워크스페이스의 기본 페이지 가져오기
        """
        try: 
            result = redis_client.get(f"user:{user_id}:workspace:{workspace_id}:default_page")
            return result if result else None
        except Exception as e:
            self.logger.error(f"워크스페이스 기본 페이지 조회 실패: {str(e)}")
            raise RedisError(f"워크스페이스 기본 페이지 조회 실패: {str(e)}")
    
    async def set_state_uuid(self, user_id: str, redis_client: redis.Redis, expire_seconds: int = 180) -> str:
        """
        OAuth 인증용 state UUID를 생성하고 Redis에 저장 (3분 만료)
        """
        try:
            state_uuid = str(uuid.uuid4())
            key = f"auth:state:{user_id}"
            self.logger.debug(f"Setting state UUID - key: {key}, uuid: {state_uuid}")
            result = redis_client.set(key, state_uuid, ex=expire_seconds)
            if not result:
                raise RedisError("State UUID 저장 실패")
            return state_uuid
        except Exception as e:
            self.logger.error(f"State UUID 생성/저장 실패: {str(e)}")
            raise RedisError(f"State UUID 생성/저장 실패: {str(e)}")

    async def validate_state_uuid(self, user_id: str, uuid_to_check: str, redis_client: redis.Redis) -> bool:
        """
        OAuth 콜백에서 state UUID 검증
        """
        try:
            key = f"auth:state:{user_id}"
            stored_uuid = redis_client.get(key)
            
            if stored_uuid:
                # 값이 일치하면 삭제하고 True 반환
                if stored_uuid == uuid_to_check:
                    redis_client.delete(key)
                    return True
            
            return False
        except Exception as e:
            self.logger.error(f"State UUID 검증 실패: {str(e)}")
            raise RedisError(f"State UUID 검증 실패: {str(e)}")
    
    async def get_func_analysis_key(self, user_id: str, commit_sha: str, filename: str, func_name: str, redis_client: redis.Redis) -> str:
        """
        함수 분석 조회
        """
        try:
            redis_key = f"{user_id}:func:{commit_sha}:{filename}:{func_name}"
            cached_result = redis_client.get(redis_key)
            return cached_result if cached_result else None
        except Exception as e:
            self.logger.error(f"함수 분석 조회 실패: {str(e)}")
            raise RedisError(f"함수 분석 조회 실패: {str(e)}")
    
    async def get_file_analysis_key(self, user_id: str, commit_sha: str, filename: str, redis_client: redis.Redis) -> str:
        """
        파일 분석 조회
        """
        try:
            redis_key = f"{user_id}:file:{commit_sha}:{filename}"
            cached_result = redis_client.get(redis_key)
            return cached_result if cached_result else None
        except Exception as e:
            self.logger.error(f"파일 분석 조회 실패: {str(e)}")
            raise RedisError(f"파일 분석 조회 실패: {str(e)}")
        
    async def set_func_analysis_key(self, analysis_result: str, user_id: str, commit_sha: str, filename: str, func_name: str, redis_client: redis.Redis) -> bool:
        """
        함수 분석 저장
        """
        try:
            redis_key = f"{user_id}:func:{commit_sha}:{filename}:{func_name}"
            result = redis_client.set(redis_key, analysis_result)
            return bool(result)
        except Exception as e:
            self.logger.error(f"함수 분석 저장 실패: {str(e)}")
            raise RedisError(f"함수 분석 저장 실패: {str(e)}")
    
    async def set_file_analysis_key(self, analysis_result: str, user_id: str, commit_sha: str, filename: str, redis_client: redis.Redis) -> bool:
        """
        파일 분석 저장
        """
        try:
            redis_key = f"{user_id}:file:{commit_sha}:{filename}"
            result = redis_client.set(redis_key, analysis_result)
            return bool(result)
        except Exception as e:
            self.logger.error(f"파일 분석 저장 실패: {str(e)}")
            raise RedisError(f"파일 분석 저장 실패: {str(e)}")
    
    async def get_db_pages(self, user_id: str, notion_db_id: str, redis_client: redis.Redis) -> list:
        """
        데이터베이스 페이지 정보를 Redis에서 가져옴
        """
        try:
            redis_key = f"user:{user_id}:db:{notion_db_id}:pages"
            cached_result = redis_client.get(redis_key)
            return json.loads(cached_result) if cached_result else None
        except Exception as e:
            self.logger.error(f"DB 페이지 조회 실패: {str(e)}")
            raise RedisError(f"DB 페이지 조회 실패: {str(e)}")
    
    async def set_db_pages(self, user_id: str, notion_db_id: str, pages: list, redis_client: redis.Redis) -> bool:
        """
        데이터베이스 페이지 정보를 Redis에 저장
        """
        try:
            redis_key = f"user:{user_id}:db:{notion_db_id}:pages"
            result = redis_client.set(redis_key, json.dumps(pages))
            return bool(result)
        except Exception as e:
            self.logger.error(f"DB 페이지 저장 실패: {str(e)}")
            raise RedisError(f"DB 페이지 저장 실패: {str(e)}")
    
    async def set_db_list(self, user_id: str, workspace_id: str, pages: list, redis_client: redis.Redis) -> bool:
        """
        사용자의 워크스페이스에 있는 모든 노션 DB들 정보를 Redis에 저장
        """
        try:
            redis_key = f"user:{user_id}:workspace:{workspace_id}:db_list"
            result = redis_client.set(redis_key, json.dumps(pages))
            return bool(result)
        except Exception as e:
            self.logger.error(f"DB 목록 저장 실패: {str(e)}")
            raise RedisError(f"DB 목록 저장 실패: {str(e)}")
    
    async def get_db_list(self, user_id: str, workspace_id: str, redis_client: redis.Redis) -> list:
        """
        사용자의 워크스페이스에 있는 모든 노션 DB들 정보를 Redis에서 가져옴
        """
        try:
            redis_key = f"user:{user_id}:workspace:{workspace_id}:db_list"
            cached_result = redis_client.get(redis_key)
            return json.loads(cached_result) if cached_result else None
        except Exception as e:
            self.logger.error(f"DB 목록 조회 실패: {str(e)}")
            raise RedisError(f"DB 목록 조회 실패: {str(e)}")
    
    async def set_default_db(self, user_id: str, default_db: str, redis_client: redis.Redis) -> bool:
        """
        사용자의 기본 노션 DB id를 Redis에 저장
        """
        try:
            redis_key = f"user:{user_id}:default_db"
            result = redis_client.set(redis_key, default_db)
            return bool(result)
        except Exception as e:
            self.logger.error(f"기본 DB 저장 실패: {str(e)}")
            raise RedisError(f"기본 DB 저장 실패: {str(e)}")
    
    async def get_default_db(self, user_id: str, redis_client: redis.Redis) -> str:
        """
        사용자의 기본 노션 DB id를 Redis에서 가져옴
        """
        try:
            redis_key = f"user:{user_id}:default_db"
            cached_result = redis_client.get(redis_key)
            return cached_result if cached_result else None
        except Exception as e:
            self.logger.error(f"기본 DB 조회 실패: {str(e)}")
            raise RedisError(f"기본 DB 조회 실패: {str(e)}")

    async def get_json(self, key: str, redis_client: redis.Redis) -> dict:
        """
        JSON 데이터를 Redis에서 가져옴
        """
        try:
            data = redis_client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            self.logger.error(f"JSON 데이터 조회 실패 (key: {key}): {str(e)}")
            raise RedisError(f"JSON 데이터 조회 실패 (key: {key}): {str(e)}")

    async def set_json(self, key: str, data: dict, redis_client: redis.Redis, expire_seconds: int = None) -> bool:
        """
        JSON 데이터를 Redis에 저장
        """
        try:
            json_data = json.dumps(data)
            if expire_seconds:
                result = redis_client.set(key, json_data, ex=expire_seconds)
            else:
                result = redis_client.set(key, json_data)
            return bool(result)
        except Exception as e:
            self.logger.error(f"JSON 데이터 저장 실패 (key: {key}): {str(e)}")
            raise RedisError(f"JSON 데이터 저장 실패 (key: {key}): {str(e)}")

    async def delete_key(self, key: str, redis_client: redis.Redis) -> bool:
        """
        Redis 키 삭제
        """
        try:
            result = redis_client.delete(key)
            return result > 0
        except Exception as e:
            self.logger.error(f"키 삭제 실패 (key: {key}): {str(e)}")
            raise RedisError(f"키 삭제 실패 (key: {key}): {str(e)}")
