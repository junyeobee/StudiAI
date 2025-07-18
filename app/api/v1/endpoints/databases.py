"""
데이터베이스 관련 API 엔드포인트
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from datetime import datetime
from app.services.notion_service import NotionService
from app.models.database import (
    DatabaseInfo,
    DatabaseCreate,
    DatabaseUpdate,
    DatabaseResponse,
    DatabaseStatus,
    DatabaseMetadata
)
from app.core.exceptions import NotionAPIError, DatabaseError
from app.utils.logger import api_logger
from app.services.supa import (
    list_all_learning_databases,
    update_learning_database_status,
    get_active_learning_database,
    insert_learning_database,
    get_db_info_by_id,
    update_learning_database
)
from app.api.v1.dependencies.auth import require_user
from app.api.v1.dependencies.workspace import get_user_workspace_with_fallback
from app.core.config import settings
from app.core.supabase_connect import get_supabase
from supabase._async.client import AsyncClient
from app.api.v1.dependencies.notion import get_notion_service
from app.services.redis_service import RedisService
from app.core.redis_connect import get_redis
from app.services.workspace_cache_service import workspace_cache_service
import redis

router = APIRouter()
redis_service = RedisService()

@router.get("/active")
async def get_active_database(workspace_id: str = Depends(get_user_workspace_with_fallback), user_id: str = Depends(require_user), redis = Depends(get_redis), supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service)):
    """현재 활성화된 DB 조회"""
    # WorkspaceCacheService로 DB 목록 가져오기
    learning_data = await workspace_cache_service.get_workspace_learning_data(workspace_id, supabase, redis)
    all_dbs = learning_data.get("databases", [])
    
    # used 상태인 DB만 찾기
    used_dbs = [db for db in all_dbs if db.get("status") == "used"]
    
    if not used_dbs:
        # 사용자가 DB를 활성화하지 않음 (사용자 실수)
        raise HTTPException(status_code=404, detail="활성화된 데이터베이스가 없습니다.")
    
    # 첫 번째 used DB의 정보 사용
    default_db_info = used_dbs[0]
    default_db_id = default_db_info.get("db_id")
    
    # Redis에 기본 DB ID 저장
    await redis_service.set_default_db(user_id, default_db_id, redis)
    
    notion_db = await notion_service.get_active_database(default_db_info)
    if not notion_db:
        # Notion API 통신 실패 (서버 측 오류)
        raise NotionAPIError("Notion API에서 데이터베이스 정보를 가져오는데 실패했습니다.")
        
    return {"status": "success", "data": notion_db}

@router.get("/available")
async def get_available_databases(workspace_id: str = Depends(get_user_workspace_with_fallback), redis = Depends(get_redis), supabase: AsyncClient = Depends(get_supabase)):
    """학습 가능한 DB 목록 조회 (used, ready 상태)"""
    # WorkspaceCacheService 사용
    learning_data = await workspace_cache_service.get_workspace_learning_data(workspace_id, supabase, redis)
    all_dbs = learning_data.get("databases", [])
    
    # used, ready 상태만 필터링
    available_dbs = [db for db in all_dbs if db.get("status") in ["used", "ready"]]
    
    return {"status": "success", "data": available_dbs}

@router.get("/", response_model=List[DatabaseInfo])
async def list_databases(workspace_id: str = Depends(get_user_workspace_with_fallback), redis = Depends(get_redis), supabase: AsyncClient = Depends(get_supabase)):
    """모든 학습 DB 목록 조회 (모든 상태)"""
    # WorkspaceCacheService 사용
    learning_data = await workspace_cache_service.get_workspace_learning_data(workspace_id, supabase, redis)
    databases = learning_data.get("databases", [])
    
    return databases

@router.get("/{db_id}", response_model=DatabaseResponse)
async def get_database(db_id: str, user_id: str = Depends(require_user), workspace_id: str = Depends(get_user_workspace_with_fallback), redis = Depends(get_redis), notion_service: NotionService = Depends(get_notion_service)):
    """DB 정보 조회"""
    database = await notion_service.get_database(db_id, workspace_id)
    return DatabaseResponse(
        status="success",
        data=database,
        message="DB 정보를 성공적으로 조회했습니다."
    )

@router.post("/", response_model=DatabaseResponse)
async def create_database(db: DatabaseCreate, user_id: str = Depends(require_user), workspace_id: str = Depends(get_user_workspace_with_fallback), redis = Depends(get_redis), supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service)):
    """새로운 DB 생성"""
    parent_page_id = await redis_service.get_default_page(user_id, workspace_id, redis)
    if not parent_page_id:
        # 사용자 설정 문제 (사용자 실수)
        raise HTTPException(status_code=404, detail="최상위 페이지의 기본값을 설정해주세요, /notion_setting/set-top-page 에서 설정해주세요.")
    
    database = await notion_service.create_database(db.title, parent_page_id)
    
    await insert_learning_database(
        db_id=database.db_id,
        title=db.title,
        parent_page_id=parent_page_id,
        supabase=supabase,
        workspace_id=workspace_id
    )
    
    # WorkspaceCacheService를 사용한 캐시 무효화
    await workspace_cache_service.invalidate_workspace_cache(workspace_id, redis)
    api_logger.info(f"새 DB 생성으로 워크스페이스 캐시 무효화: {workspace_id}")
    
    return DatabaseResponse(
        status="success",
        data=database,
        message="DB 성공적으로 생성되었습니다, Github 연동 설정을 하려면 레포지터리 링크를 포함하고, github.create_webhook 액션을 호출해주세요."
    )

@router.put("/{db_id}", response_model=DatabaseResponse)
async def update_database(db_id: str, db_update: DatabaseUpdate, workspace_id: str = Depends(get_user_workspace_with_fallback), redis = Depends(get_redis), supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service)):
    """DB 정보 업데이트"""
    notion_db = await notion_service.update_database(db_id, db_update)
    
    update_data = db_update.dict()
    if update_data:
        db_info = await update_learning_database(db_id, update_data, supabase, workspace_id)
    else:
        db_info = await get_db_info_by_id(db_id, supabase, workspace_id)
    await workspace_cache_service.invalidate_workspace_cache(workspace_id, redis)
    
    if not db_info:
        # 데이터베이스를 찾을 수 없음 (사용자 실수 - 잘못된 ID)
        raise HTTPException(status_code=404, detail="데이터베이스를 찾을 수 없습니다.")
        
    return DatabaseResponse(
        status="success",
        data=DatabaseInfo(
            db_id=notion_db.db_id,
            title=notion_db.title,
            parent_page_id=notion_db.parent_page_id,
            status=db_info.get("status", DatabaseStatus.READY),
            last_used_date=db_info.get("last_used_date", datetime.now()),
            webhook_id=db_info.get("webhook_id"),
            webhook_status=db_info.get("webhook_status", "inactive"),
            workspace_id=workspace_id
        ),
        message="데이터베이스 정보가 성공적으로 업데이트되었습니다."
    )

@router.post("/{db_id}/activate")
async def activate_database(db_id: str, workspace_id: str = Depends(get_user_workspace_with_fallback), redis = Depends(get_redis), supabase: AsyncClient = Depends(get_supabase)):
    """데이터베이스 활성화"""
    result = await update_learning_database_status(db_id, "used", supabase, workspace_id)
    await workspace_cache_service.invalidate_workspace_cache(workspace_id, redis)
    
    if not result:
        # 데이터베이스를 찾을 수 없음 (사용자 실수 - 잘못된 ID)
        raise HTTPException(status_code=404, detail="데이터베이스를 찾을 수 없습니다.")
    
    return {"status": "success", "message": "데이터베이스가 활성화되었습니다."}

@router.post("/deactivate")
async def deactivate_all_databases(workspace_id: str = Depends(get_user_workspace_with_fallback), redis = Depends(get_redis), supabase: AsyncClient = Depends(get_supabase)):
    """활성화된 DB를 비활성화 상태로 변경합니다."""
    result = await update_learning_database_status(db_id=None, status="ready", supabase=supabase, workspace_id=workspace_id)
    await workspace_cache_service.invalidate_workspace_cache(workspace_id, redis)
    api_logger.info(f"모든 DB 비활성화로 워크스페이스 캐시 무효화: {workspace_id}")
    
    if not result:
        # 활성화된 데이터베이스가 없음 (사용자 실수)
        raise HTTPException(status_code=404, detail="활성화된 데이터베이스가 없습니다.")
    
    return {"status":"success", "message":"모든 데이터베이스를 비활성화했습니다."}

@router.get("/pages/{page_id}/databases", response_model=List[DatabaseMetadata])
async def get_page_databases(page_id: str, workspace_id: str = Depends(get_user_workspace_with_fallback), redis = Depends(get_redis), notion_service: NotionService = Depends(get_notion_service)):
    """페이지 내의 모든 데이터베이스 목록 조회"""
    databases = await notion_service.list_databases_in_page(page_id, workspace_id)
    return databases 

