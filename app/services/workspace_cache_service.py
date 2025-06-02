"""
워크스페이스 캐싱 전용 서비스
"""
from typing import Dict, Any
import redis
from supabase._async.client import AsyncClient
from app.services.redis_service import RedisService
from app.utils.logger import api_logger


class WorkspaceCacheService:
    """워크스페이스 학습 데이터 캐싱 서비스"""
    
    def __init__(self):
        self.redis_service = RedisService()
        self.cache_ttl = 600
        
    async def get_workspace_learning_data(self, workspace_id: str, supabase: AsyncClient, redis_client: redis.Redis) -> Dict[str, Any]:
        """워크스페이스의 학습 DB와 페이지 데이터 조회 (Redis 캐싱 활용)"""
        try:
            # Redis에서 캐시된 데이터 조회
            cache_key = self._get_cache_key(workspace_id)
            cached_data = await self.redis_service.get_json(cache_key, redis_client)
            
            if cached_data:
                api_logger.info(f"Redis에서 워크스페이스 {workspace_id} 학습 데이터 조회")
                return cached_data
            
            # 캐시 미스 - DB에서 조회
            api_logger.info(f"DB에서 워크스페이스 {workspace_id} 학습 데이터 조회")
            
            db_result = await supabase.table("learning_databases").select("*").eq("workspace_id", workspace_id).is_("orphaned_at", None).execute()
            learning_dbs = db_result.data
            
            if not learning_dbs:
                empty_data = {"databases": [], "pages": [], "entity_map": {}}
                await self.redis_service.set_json(cache_key, empty_data, redis_client, expire_seconds=self.cache_ttl)
                return empty_data
            
            db_ids = [db["id"] for db in learning_dbs]
            pages_result = await supabase.table("learning_pages").select("*").in_("learning_db_id", db_ids).execute()
            learning_pages = pages_result.data
            
            entity_map = self._build_entity_map(learning_dbs, learning_pages)
            
            learning_data = {
                "databases": learning_dbs,
                "pages": learning_pages,
                "entity_map": entity_map
            }
            
            await self.redis_service.set_json(cache_key, learning_data, redis_client, expire_seconds=self.cache_ttl)
            api_logger.info(f"워크스페이스 {workspace_id} 학습 데이터 캐시 저장 완료")
            
            return learning_data
            
        except Exception as e:
            api_logger.error(f"워크스페이스 학습 데이터 조회 실패: {str(e)}")
            return {"databases": [], "pages": [], "entity_map": {}}
    
    async def invalidate_workspace_cache(self, workspace_id: str, redis_client: redis.Redis) -> bool:
        """워크스페이스 캐시 무효화"""
        try:
            cache_key = self._get_cache_key(workspace_id)
            result = await self.redis_service.delete_key(cache_key, redis_client)
            if result:
                api_logger.info(f"워크스페이스 캐시 무효화 완료: {workspace_id}")
            else:
                api_logger.info(f"워크스페이스 캐시가 존재하지 않음: {workspace_id}")
            return result
        except Exception as e:
            api_logger.error(f"워크스페이스 캐시 무효화 실패: {str(e)}")
            return False
    
    async def refresh_workspace_cache(self, workspace_id: str, supabase: AsyncClient, redis_client: redis.Redis) -> Dict[str, Any]:
        """워크스페이스 캐시 강제 갱신"""
        try:
            await self.invalidate_workspace_cache(workspace_id, redis_client)
            return await self.get_workspace_learning_data(workspace_id, supabase, redis_client)
        except Exception as e:
            api_logger.error(f"워크스페이스 캐시 갱신 실패: {str(e)}")
            return {"databases": [], "pages": [], "entity_map": {}}
    
    def _get_cache_key(self, workspace_id: str) -> str:
        """캐시 키 생성"""
        return f"workspace:{workspace_id}:learning_data"
    
    def _build_entity_map(self, learning_dbs: list, learning_pages: list) -> Dict[str, Any]:
        """빠른 검색을 위한 entity_map 생성"""
        entity_map = {}
        
        for db in learning_dbs:
            entity_map[db["db_id"]] = {"type": "database", "db_id": db["db_id"], "system_id": db["id"]}
            if db["parent_page_id"]:
                entity_map[db["parent_page_id"]] = {"type": "db_parent_page", "db_id": db["db_id"], "system_id": db["id"]}
                
        for page in learning_pages:
            entity_map[page["page_id"]] = {"type": "learning_page", "page_id": page["page_id"], "system_id": page["id"], "db_id": page["learning_db_id"]}
            if page["ai_block_id"]:
                entity_map[page["ai_block_id"]] = {"type": "ai_block", "page_id": page["page_id"], "system_id": page["id"], "db_id": page["learning_db_id"]}
        
        return entity_map

workspace_cache_service = WorkspaceCacheService() 