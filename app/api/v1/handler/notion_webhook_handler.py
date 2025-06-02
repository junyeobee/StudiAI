"""
Notion 웹훅 이벤트 핸들러
"""
from app.utils.logger import api_logger
from app.services.redis_service import RedisService
from app.services.workspace_cache_service import workspace_cache_service
from app.services.supa import (
    delete_learning_page_by_system_id,
    clear_ai_block_id,
    delete_learning_database_by_system_id
)
from supabase._async.client import AsyncClient
from typing import Dict, Any
import json
import redis
from datetime import datetime

class NotionWebhookHandler:
    """Notion 웹훅 이벤트 처리 클래스"""
    
    def __init__(self):
        self.redis_service = RedisService()
    
    async def process_webhook_event(self, payload: dict, supabase: AsyncClient, redis_client: redis.Redis):
        """웹훅 이벤트 처리 로직"""
        try:
            workspace_id = payload.get("workspace_id")
            event_type = payload.get("type")
            entity = payload.get("entity", {})
            entity_id = entity.get("id")
            
            if not entity_id:
                api_logger.warning("entity.id가 없는 웹훅 이벤트")
                return
            
            # WorkspaceCacheService를 사용한 학습 데이터 조회
            learning_data = await workspace_cache_service.get_workspace_learning_data(workspace_id, supabase, redis_client)
            entity_map = learning_data.get("entity_map", {})
            
            # entity_id가 학습 관련 엔티티인지 확인
            entity_info = entity_map.get(entity_id)
            
            # entity_map에 없으면 DB에서 직접 조회 (Fallback)
            if not entity_info:
                entity_info = await self.check_entity_in_database(entity_id, workspace_id, supabase)
                
                if entity_info:
                    # 발견된 엔티티를 캐시에 추가하고 캐시 갱신
                    api_logger.info(f"새로운 학습 엔티티 발견, 캐시 갱신: {entity_id}")
                    await workspace_cache_service.refresh_workspace_cache(workspace_id, supabase, redis_client)
                else:
                    api_logger.info(f"학습과 무관한 엔티티: {entity_id}, 이벤트 무시")
                    return
            
            # 학습 관련 엔티티 발견!
            api_logger.info(f"학습 관련 이벤트 감지: {event_type} - {entity_info['type']} ({entity_id})")
            
            # 이벤트 타입별 처리
            match event_type:
                case "page.deleted":
                    await self.handle_page_deleted(entity_info, payload, supabase, redis_client)
                case "page.content_updated":
                    await self.handle_page_content_updated(entity_info, payload, supabase, redis_client)
                case "database.deleted":
                    await self.handle_database_deleted(entity_info, payload, supabase, redis_client)
                case "database.updated":
                    await self.handle_database_updated(entity_info, payload, supabase, redis_client)
                case _:
                    api_logger.info(f"처리하지 않는 이벤트 타입: {event_type}")
            
            # 처리 완료 후 캐시 무효화
            await workspace_cache_service.invalidate_workspace_cache(workspace_id, redis_client)
            api_logger.info(f"이벤트 처리 완료 및 캐시 무효화: {event_type} - {entity_info['type']}")
            
        except Exception as e:
            api_logger.error(f"웹훅 이벤트 처리 실패: {str(e)}")
    
    async def check_entity_in_database(self, entity_id: str, workspace_id: str, supabase: AsyncClient) -> dict:
        """entity_id가 학습 관련 엔티티인지 DB에서 직접 조회 (Fallback)"""
        try:
            # 1. 학습 DB인지 확인
            db_result = await supabase.table("learning_databases").select("*").eq("db_id", entity_id).eq("workspace_id", workspace_id).is_("orphaned_at", None).execute()
            if db_result.data:
                db = db_result.data[0]
                return {"type": "database", "db_id": db["db_id"], "system_id": db["id"]}
            
            # 2. DB 부모 페이지인지 확인
            parent_page_result = await supabase.table("learning_databases").select("*").eq("parent_page_id", entity_id).eq("workspace_id", workspace_id).is_("orphaned_at", None).execute()
            if parent_page_result.data:
                db = parent_page_result.data[0]
                return {"type": "db_parent_page", "db_id": db["db_id"], "system_id": db["id"]}
            
            # 3. 학습 페이지인지 확인 - learning_databases와 조인해서 workspace_id와 orphaned_at 확인
            page_result = await supabase.table("learning_pages").select("*, learning_databases!inner(workspace_id, db_id)").eq("page_id", entity_id).eq("learning_databases.workspace_id", workspace_id).is_("learning_databases.orphaned_at", None).execute()
            if page_result.data:
                page = page_result.data[0]
                return {
                    "type": "learning_page", 
                    "page_id": page["page_id"], 
                    "system_id": page["id"], 
                    "db_id": page["learning_db_id"]
                }
            
            # 4. AI 블록인지 확인 - learning_pages와 learning_databases 조인
            ai_block_result = await supabase.table("learning_pages").select("*, learning_databases!inner(workspace_id, db_id)").eq("ai_block_id", entity_id).eq("learning_databases.workspace_id", workspace_id).is_("learning_databases.orphaned_at", None).execute()
            if ai_block_result.data:
                page = ai_block_result.data[0]
                return {
                    "type": "ai_block",
                    "page_id": page["page_id"],
                    "system_id": page["id"], 
                    "db_id": page["learning_db_id"]
                }
            
            return None
            
        except Exception as e:
            api_logger.error(f"엔티티 DB 조회 실패: {str(e)}")
            return None
    
    async def handle_page_deleted(self, entity_info: Dict[str, Any], payload: Dict[str, Any], supabase: AsyncClient, redis_client: redis.Redis) -> None:
        """페이지 삭제 이벤트 처리"""
        try:
            entity_type = entity_info.get("type")
            entity_id = payload.get("entity", {}).get("id")
            workspace_id = payload.get("workspace_id")
            
            api_logger.info(f"페이지 삭제 처리 시작: {entity_type} - {entity_id}")
            
            match entity_type:
                case "learning_page":
                    # 학습 페이지 삭제 처리
                    await self._handle_learning_page_deleted(entity_info, payload, supabase)
                case "db_parent_page":
                    # DB 부모 페이지 삭제는 배치에서 처리
                    pass
                case "ai_block":
                    # AI 블록 삭제 처리
                    await self._handle_ai_block_deleted(entity_info, payload, supabase)
            
            # 캐시에서 해당 엔티티만 제거
            await self._remove_entity_from_cache(workspace_id, entity_id, redis_client)
            
            api_logger.info(f"페이지 삭제 처리 완료: {entity_type}")
            
        except Exception as e:
            api_logger.error(f"페이지 삭제 처리 실패: {str(e)}")
    
    async def handle_page_content_updated(self, entity_info: Dict[str, Any], payload: Dict[str, Any], supabase: AsyncClient, redis_client: redis.Redis) -> None:
        """페이지 콘텐츠 업데이트 이벤트 처리"""
        try:
            entity_type = entity_info.get("type")
            entity_id = payload.get("entity", {}).get("id")
            workspace_id = payload.get("workspace_id")
            updated_blocks = payload.get("data", {}).get("updated_blocks", [])
            
            api_logger.info(f"페이지 콘텐츠 업데이트 처리 시작: {entity_type} - {entity_id}")
            api_logger.info(f"업데이트된 블록 수: {len(updated_blocks)}")
            
            # 콘텐츠 업데이트는 캐시 무효화 불필요 (entity_map 변경 없음)
            # 모든 업데이트는 트리거로 자동 처리됨
            api_logger.info(f"페이지 콘텐츠 업데이트 처리 완료: {entity_type}")
            
        except Exception as e:
            api_logger.error(f"페이지 콘텐츠 업데이트 처리 실패: {str(e)}")
    
    async def handle_database_deleted(self, entity_info: Dict[str, Any], payload: Dict[str, Any], supabase: AsyncClient, redis_client: redis.Redis) -> None:
        """데이터베이스 삭제 이벤트 처리"""
        try:
            system_id = entity_info.get("system_id")  # 시스템 UUID
            db_id = entity_info.get("db_id")  # 실제 Notion DB ID
            entity_id = payload.get("entity", {}).get("id")
            workspace_id = payload.get("workspace_id")
            
            api_logger.info(f"데이터베이스 삭제 이벤트 감지: {entity_id}")
            
            # 데이터베이스가 실제로 삭제되면 복구 불가능하므로 즉시 삭제
            success = await delete_learning_database_by_system_id(system_id, supabase)
            if success:
                api_logger.info(f"데이터베이스 레코드 삭제 완료: {db_id} (시스템 ID: {system_id})")
            
            # 캐시에서 해당 엔티티만 제거 (전체 무효화 아님)
            await self._remove_entity_from_cache(workspace_id, entity_id, redis_client)
            
            api_logger.info(f"데이터베이스 삭제 이벤트 처리 완료: {entity_id}")
            
        except Exception as e:
            api_logger.error(f"데이터베이스 삭제 이벤트 처리 실패: {str(e)}")
    
    async def handle_database_updated(self, entity_info: Dict[str, Any], payload: Dict[str, Any], supabase: AsyncClient, redis_client: redis.Redis) -> None:
        """데이터베이스 업데이트 이벤트 처리"""
        try:
            system_id = entity_info.get("system_id")
            db_id = entity_info.get("db_id")
            entity_id = payload.get("entity", {}).get("id")
            workspace_id = payload.get("workspace_id")
            
            api_logger.info(f"데이터베이스 업데이트 처리 시작: {entity_id}")
            
            api_logger.info(f"데이터베이스 업데이트 감지 (트리거 자동 처리): {db_id} (시스템 ID: {system_id})")
            
            api_logger.info(f"데이터베이스 업데이트 처리 완료: {entity_id}")
            
        except Exception as e:
            api_logger.error(f"데이터베이스 업데이트 처리 실패: {str(e)}")
    
    async def _handle_learning_page_deleted(self, entity_info: Dict[str, Any], payload: Dict[str, Any], supabase: AsyncClient) -> None:
        """학습 페이지 삭제 처리"""
        system_id = entity_info.get("system_id")
        page_id = entity_info.get("page_id")
        
        # supa.py 함수 사용
        success = await delete_learning_page_by_system_id(system_id, supabase)
        
        if success:
            api_logger.info(f"학습 페이지 삭제 완료: {page_id} (시스템 ID: {system_id})")
        else:
            api_logger.warning(f"삭제할 학습 페이지를 찾을 수 없음: {page_id} (시스템 ID: {system_id})")
    
    async def _handle_ai_block_deleted(self, entity_info: Dict[str, Any], payload: Dict[str, Any], supabase: AsyncClient) -> None:
        """AI 블록 삭제 처리"""
        system_id = entity_info.get("system_id")
        page_id = entity_info.get("page_id")
        
        # supa.py 함수 사용
        success = await clear_ai_block_id(system_id, supabase)
        
        if success:
            api_logger.info(f"AI 블록 삭제 처리 완료: 페이지 {page_id} (시스템 ID: {system_id})")
    
    async def _remove_entity_from_cache(self, workspace_id: str, entity_id: str, redis_client: redis.Redis) -> None:
        """캐시에서 특정 엔티티만 제거"""
        try:
            cache_key = f"workspace:{workspace_id}:learning_data"
            learning_data = await self.redis_service.get_json(cache_key, redis_client)
            
            if not learning_data or "entity_map" not in learning_data:
                api_logger.info(f"캐시에 데이터가 없어 엔티티 제거 스킵: {entity_id}")
                return
            
            # entity_map에서 해당 엔티티 제거
            if entity_id in learning_data["entity_map"]:
                del learning_data["entity_map"][entity_id]
                # 수정된 데이터 다시 저장 (TTL 유지)
                await self.redis_service.set_json(cache_key, learning_data, redis_client, expire_seconds=600)
                api_logger.info(f"캐시에서 엔티티 제거 완료: {entity_id}")
            else:
                api_logger.info(f"캐시에 해당 엔티티 없음: {entity_id}")
                
        except Exception as e:
            api_logger.error(f"캐시에서 엔티티 제거 실패: {str(e)}")

# 핸들러 인스턴스 생성
webhook_handler = NotionWebhookHandler() 