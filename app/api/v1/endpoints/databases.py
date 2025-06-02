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
from app.api.v1.dependencies.workspace import get_user_workspace
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

# 완료
@router.get("/active")
async def get_active_database(workspace_id: str = Depends(get_user_workspace), user_id: str = Depends(require_user), redis = Depends(get_redis), supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service)):
    """현재 활성화된 DB 조회"""
    try:
        # Supabase에서 활성 데이터베이스 정보 조회
        default_db_id = await redis_service.get_default_db(user_id, redis)
        default_db_info = None
        
        if not default_db_id:
            # Redis에 없으면 Supabase에서 조회
            default_db_info = await get_active_learning_database(supabase, workspace_id)
            if not default_db_info:
                return {"status": "none", "message": "활성화된 데이터베이스가 없습니다."}
            
            # db_id만 추출해서 Redis에 저장
            default_db_id = default_db_info.get("db_id")
            await redis_service.set_default_db(user_id, default_db_id, redis)
        else:
            # Redis에서 db_id를 가져왔으면 전체 정보를 다시 조회
            default_db_info = await get_db_info_by_id(default_db_id, supabase, workspace_id)
            if not default_db_info:
                return {"status": "none", "message": "활성화된 데이터베이스가 없습니다."}
            
        notion_db = await notion_service.get_active_database(default_db_info)
        if not notion_db:
            return {"status": "error", "message": "Notion API에서 데이터베이스 정보를 가져오는데 실패했습니다."}
            
        return {"status": "success", "data": notion_db}
    except Exception as e:
        api_logger.error(f"활성화된 DB 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/available")
async def get_available_databases(workspace_id: str = Depends(get_user_workspace), redis = Depends(get_redis), supabase: AsyncClient = Depends(get_supabase)):
    """학습 가능한 DB 목록 조회 (used, ready 상태)"""
    try:
        # WorkspaceCacheService 사용
        learning_data = await workspace_cache_service.get_workspace_learning_data(workspace_id, supabase, redis)
        all_dbs = learning_data.get("databases", [])
        
        # used, ready 상태만 필터링
        available_dbs = [db for db in all_dbs if db.get("status") in ["used", "ready"]]
        
        return {"status": "success", "data": available_dbs}
    except Exception as e:
        api_logger.error(f"학습 가능한 DB 목록 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[DatabaseInfo])
async def list_databases(workspace_id: str = Depends(get_user_workspace), redis = Depends(get_redis), supabase: AsyncClient = Depends(get_supabase)):
    """모든 학습 DB 목록 조회 (모든 상태)"""
    try:
        # WorkspaceCacheService 사용
        learning_data = await workspace_cache_service.get_workspace_learning_data(workspace_id, supabase, redis)
        databases = learning_data.get("databases", [])
        
        return databases
    except Exception as e:
        api_logger.error(f"모든 학습 DB 목록 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 완료
@router.get("/{db_id}", response_model=DatabaseResponse)
async def get_database(db_id: str, workspace_id: str = Depends(get_user_workspace), redis = Depends(get_redis), notion_service: NotionService = Depends(get_notion_service)):
    """DB 정보 조회"""
    try:
        #db_key = await get_db_key(db_id, user_id)
        database = await notion_service.get_database(db_id, workspace_id)
        return DatabaseResponse(
            status="success",
            data=database,
            message="DB 정보를 성공적으로 조회했습니다."
        )
    except NotionAPIError as e:
        api_logger.error(f"DB 정보 조회 실패: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))

# 완료
@router.post("/", response_model=DatabaseResponse)
async def create_database(db: DatabaseCreate, workspace_id: str = Depends(get_user_workspace), redis = Depends(get_redis), supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service)):
    """새로운 DB 생성"""
    try:
        parent_page_id = await redis_service.get_default_page(workspace_id, redis)
        if not parent_page_id:
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
    except NotionAPIError as e:
        api_logger.error(f"DB 생성 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 완료
@router.put("/{db_id}", response_model=DatabaseResponse)
async def update_database(db_id: str, db_update: DatabaseUpdate, workspace_id: str = Depends(get_user_workspace), redis = Depends(get_redis), supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service)):
    """DB 정보 업데이트"""
    try:
        notion_db = await notion_service.update_database(db_id, db_update, workspace_id)
        
        update_data = db_update.dict()
        if update_data:
            db_info = await update_learning_database(db_id, update_data, supabase, workspace_id)
        else:
            db_info = await get_db_info_by_id(db_id, supabase, workspace_id)
            
        if not db_info:
            raise HTTPException(
                status_code=404,
                detail="데이터베이스를 찾을 수 없습니다."
            )
            
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
    except NotionAPIError as e:
        api_logger.error(f"DB 업데이트 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 완료
@router.post("/{db_id}/activate")
async def activate_database(db_id: str, workspace_id: str = Depends(get_user_workspace), redis = Depends(get_redis), supabase: AsyncClient = Depends(get_supabase)):
    """데이터베이스 활성화"""
    try:
        result = await update_learning_database_status(db_id, "used", supabase, workspace_id)
        if not result:
            raise HTTPException(status_code=404, detail="데이터베이스를 찾을 수 없습니다.")
        return {"status": "success", "message": "데이터베이스가 활성화되었습니다."}
    except Exception as e:
        api_logger.error(f"DB 활성화 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 완료
@router.post("/deactivate")
async def deactivate_all_databases(workspace_id: str = Depends(get_user_workspace), redis = Depends(get_redis), supabase: AsyncClient = Depends(get_supabase)):
    """활성화된 DB를 비활성화 상태로 변경합니다."""
    try:
        result = await update_learning_database_status(db_id=None, status="ready", supabase=supabase, workspace_id=workspace_id)
        if not result:
            raise HTTPException(404, "활성화된 데이터베이스가 없습니다.")
        return {"status":"success", "message":"모든 데이터베이스를 비활성화했습니다."}
    except Exception as e:
        api_logger.error(f"모든 DB 비활성화 실패: {str(e)}")
        raise HTTPException(500, str(e))

# 완료
@router.get("/pages/{page_id}/databases", response_model=List[DatabaseMetadata])
async def get_page_databases(page_id: str, workspace_id: str = Depends(get_user_workspace), redis = Depends(get_redis), notion_service: NotionService = Depends(get_notion_service)):
    """페이지 내의 모든 데이터베이스 목록 조회"""
    try:
        #db_key = await get_db_key(page_id, user_id)
        databases = await notion_service.list_databases_in_page(page_id, workspace_id)
        return databases
    except Exception as e:
        api_logger.error(f"페이지 내의 데이터베이스 목록 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 

