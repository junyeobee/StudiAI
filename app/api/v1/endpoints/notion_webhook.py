from fastapi import APIRouter, Request, HTTPException, Depends
from app.utils.logger import api_logger
from app.core.supabase_connect import get_supabase
from app.services.redis_service import RedisService
from app.core.redis_connect import get_redis
from app.api.v1.handler.notion_webhook_handler import webhook_handler
from supabase._async.client import AsyncClient
import hmac
import hashlib
import json
import redis
from app.core.config import settings

router = APIRouter()
redis_service = RedisService()

def verify_signature(body: bytes, received_signature: str) -> bool:
    """Notion 웹훅 시그니처 검증"""
    try:
        # HMAC-SHA256으로 예상 시그니처 생성
        expected_signature = hmac.new(
            settings.NOTION_WEBHOOK_SECRET.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()
        
        # 받은 시그니처에서 'sha256=' 접두사 제거
        if received_signature.startswith('sha256='):
            received_hash = received_signature[7:]  # 'sha256=' 제거
        else:
            return False
            
        # 시그니처 비교 (타이밍 공격 방지를 위해 hmac.compare_digest 사용)
        return hmac.compare_digest(expected_signature, received_hash)
        
    except Exception as e:
        api_logger.error(f"시그니처 검증 실패: {str(e)}")
        return False

@router.post("/")
async def handle_notion_webhook(
    request: Request,
    supabase: AsyncClient = Depends(get_supabase),
    redis_client: redis.Redis = Depends(get_redis)
):
    """Master Integration으로부터 웹훅 이벤트 수신"""
    try:
        # 헤더 및 바디 파싱
        headers = request.headers
        body = await request.body()
        
        # 시그니처 검증
        notion_signature = headers.get("x-notion-signature")
        if not notion_signature:
            api_logger.warning("시그니처 헤더가 없음")
            raise HTTPException(status_code=401, detail="Missing signature header")
            
        if not verify_signature(body, notion_signature):
            api_logger.warning(f"잘못된 시그니처: {notion_signature}")
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        api_logger.info("시그니처 검증 성공")
        
        payload = json.loads(body.decode())
        
        api_logger.info(f"웹훅 수신: {payload.get('type')} from workspace {payload.get('workspace_id')}")
        
        await process_webhook_event(payload, supabase, redis_client)
        
        # 즉시 200 응답
        return {"status": "success"}
        
    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(f"웹훅 처리 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def get_workspace_learning_data(workspace_id: str, supabase: AsyncClient, redis_client: redis.Redis):
    """워크스페이스의 학습 DB와 페이지 데이터 조회 (Redis 캐싱 활용)"""
    try:
        # Redis에서 캐시된 데이터 조회
        cache_key = f"workspace:{workspace_id}:learning_data"
        cached_data = await redis_service.get_json(cache_key, redis_client)
        
        if cached_data:
            api_logger.info(f"Redis에서 워크스페이스 {workspace_id} 학습 데이터 조회")
            return cached_data
        
        # 캐시 미스 - DB에서 조회
        api_logger.info(f"DB에서 워크스페이스 {workspace_id} 학습 데이터 조회")
        
        # 1. 학습 DB 목록 조회
        db_result = await supabase.table("learning_databases").select("*").eq("workspace_id", workspace_id).eq("status", "ready").is_("orphaned_at", None).execute()
        learning_dbs = db_result.data
        
        if not learning_dbs:
            return {"databases": [], "pages": [], "entity_map": {}}
        
        # 2. 각 DB의 페이지들 조회
        db_ids = [db["id"] for db in learning_dbs]
        pages_result = await supabase.table("learning_pages").select("*").in_("learning_db_id", db_ids).execute()
        learning_pages = pages_result.data
        
        # 3. 빠른 검색을 위한 entity_map 생성
        entity_map = {}
        
        # DB 관련 엔티티들 매핑 - 실제 Notion DB ID를 키로 사용
        for db in learning_dbs:
            entity_map[db["db_id"]] = {"type": "database", "db_id": db["db_id"], "system_id": db["id"]}
            if db["parent_page_id"]:
                entity_map[db["parent_page_id"]] = {"type": "db_parent_page", "db_id": db["db_id"], "system_id": db["id"]}
            
        # 페이지 관련 엔티티들 매핑 - 실제 Notion Page ID를 키로 사용
        for page in learning_pages:
            entity_map[page["page_id"]] = {"type": "learning_page", "page_id": page["page_id"], "system_id": page["id"], "db_id": page["learning_db_id"]}
            if page["ai_block_id"]:
                entity_map[page["ai_block_id"]] = {"type": "ai_block", "page_id": page["page_id"], "system_id": page["id"], "db_id": page["learning_db_id"]}
        
        learning_data = {
            "databases": learning_dbs,
            "pages": learning_pages,
            "entity_map": entity_map
        }
        
        # Redis에 캐시 저장 (10분 TTL)
        await redis_service.set_json(cache_key, learning_data, redis_client, expire_seconds=600)
        
        return learning_data
        
    except Exception as e:
        api_logger.error(f"워크스페이스 학습 데이터 조회 실패: {str(e)}")
        return {"databases": [], "pages": [], "entity_map": {}}

async def process_webhook_event(payload: dict, supabase: AsyncClient, redis_client: redis.Redis):
    """웹훅 이벤트 처리 로직"""
    try:
        workspace_id = payload.get("workspace_id")
        event_type = payload.get("type")
        entity = payload.get("entity", {})
        entity_id = entity.get("id")
        
        if not entity_id:
            api_logger.warning("entity.id가 없는 웹훅 이벤트")
            return
        
        # 워크스페이스의 학습 관련 데이터 조회
        learning_data = await get_workspace_learning_data(workspace_id, supabase, redis_client)
        entity_map = learning_data.get("entity_map", {})
        
        # entity_id가 학습 관련 엔티티인지 확인
        entity_info = entity_map.get(entity_id)
        
        # entity_map에 없으면 DB에서 직접 조회 (Fallback)
        if not entity_info:
            entity_info = await check_entity_in_database(entity_id, workspace_id, supabase)
            
            if entity_info:
                # 발견된 엔티티를 캐시에 추가하고 캐시 갱신
                api_logger.info(f"새로운 학습 엔티티 발견, 캐시 갱신: {entity_id}")
                await refresh_workspace_cache(workspace_id, supabase, redis_client)
            else:
                api_logger.info(f"학습과 무관한 엔티티: {entity_id}, 이벤트 무시")
                return
        
        # 학습 관련 엔티티 발견!
        api_logger.info(f"학습 관련 이벤트 감지: {event_type} - {entity_info['type']} ({entity_id})")
        
        # 이벤트 타입별 처리 (웹훅 핸들러 사용)
        match event_type:
            case "page.deleted":
                await webhook_handler.handle_page_deleted(entity_info, payload, supabase, redis_client)
            case "page.content_updated":
                await webhook_handler.handle_page_content_updated(entity_info, payload, supabase, redis_client)
            case "database.deleted":
                await webhook_handler.handle_database_deleted(entity_info, payload, supabase, redis_client)
            case "database.updated":
                await webhook_handler.handle_database_updated(entity_info, payload, supabase, redis_client)
            case _:
                api_logger.info(f"처리하지 않는 이벤트 타입: {event_type}")
        
        # 처리 완료
        api_logger.info(f"이벤트 처리 완료: {event_type} - {entity_info['type']}")
        
    except Exception as e:
        api_logger.error(f"웹훅 이벤트 처리 실패: {str(e)}")

async def check_entity_in_database(entity_id: str, workspace_id: str, supabase: AsyncClient) -> dict:
    """entity_id가 학습 관련 엔티티인지 DB에서 직접 조회 (Fallback)"""
    try:
        # 1. 학습 DB인지 확인
        db_result = await supabase.table("learning_databases").select("*").eq("db_id", entity_id).eq("workspace_id", workspace_id).eq("status", "ready").is_("orphaned_at", None).execute()
        if db_result.data:
            db = db_result.data[0]
            return {"type": "database", "db_id": db["db_id"], "system_id": db["id"]}
        
        # 2. DB 부모 페이지인지 확인
        parent_page_result = await supabase.table("learning_databases").select("*").eq("parent_page_id", entity_id).eq("workspace_id", workspace_id).eq("status", "ready").is_("orphaned_at", None).execute()
        if parent_page_result.data:
            db = parent_page_result.data[0]
            return {"type": "db_parent_page", "db_id": db["db_id"], "system_id": db["id"]}
        
        # 3. 학습 페이지인지 확인 - learning_databases와 조인해서 workspace_id 확인
        page_result = await supabase.table("learning_pages").select("*, learning_databases!inner(workspace_id, db_id)").eq("page_id", entity_id).eq("learning_databases.workspace_id", workspace_id).execute()
        if page_result.data:
            page = page_result.data[0]
            return {
                "type": "learning_page", 
                "page_id": page["page_id"], 
                "system_id": page["id"], 
                "db_id": page["learning_db_id"]
            }
        
        # 4. AI 블록인지 확인 - learning_pages와 learning_databases 조인
        ai_block_result = await supabase.table("learning_pages").select("*, learning_databases!inner(workspace_id, db_id)").eq("ai_block_id", entity_id).eq("learning_databases.workspace_id", workspace_id).execute()
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

async def refresh_workspace_cache(workspace_id: str, supabase: AsyncClient, redis_client: redis.Redis):
    """워크스페이스 캐시 강제 갱신"""
    try:
        cache_key = f"workspace:{workspace_id}:learning_data"
        await redis_service.delete_key(cache_key, redis_client)
        # 새로 조회해서 캐시 재생성
        await get_workspace_learning_data(workspace_id, supabase, redis_client)
        api_logger.info(f"워크스페이스 캐시 갱신 완료: {workspace_id}")
    except Exception as e:
        api_logger.error(f"캐시 갱신 실패: {str(e)}")

async def remove_entity_from_cache(workspace_id: str, entity_id: str, redis_client: redis.Redis):
    """캐시에서 특정 엔티티만 제거"""
    try:
        cache_key = f"workspace:{workspace_id}:learning_data"
        learning_data = await redis_service.get_json(cache_key, redis_client)
        
        if not learning_data or "entity_map" not in learning_data:
            api_logger.info(f"캐시에 데이터가 없어 엔티티 제거 스킵: {entity_id}")
            return
        
        # entity_map에서 해당 엔티티 제거
        if entity_id in learning_data["entity_map"]:
            del learning_data["entity_map"][entity_id]
            # 수정된 데이터 다시 저장 (TTL 유지)
            await redis_service.set_json(cache_key, learning_data, redis_client, expire_seconds=600)
            api_logger.info(f"캐시에서 엔티티 제거 완료: {entity_id}")
        else:
            api_logger.info(f"캐시에 해당 엔티티 없음: {entity_id}")
            
    except Exception as e:
        api_logger.error(f"캐시에서 엔티티 제거 실패: {str(e)}")
