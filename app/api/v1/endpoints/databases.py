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
from app.core.config import settings
from app.core.supabase_connect import get_supabase
from supabase._async.client import AsyncClient
from app.api.v1.dependencies.notion import get_notion_service

router = APIRouter()

# 완료
@router.get("/active")
async def get_active_database(user_id: str = Depends(require_user), supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service)):
    """현재 활성화된 DB 조회"""
    try:
        # Supabase에서 활성 데이터베이스 정보 조회
        db_info = await get_active_learning_database(supabase, user_id)
        if not db_info:
            return {"status": "none", "message": "활성화된 데이터베이스가 없습니다."}
            
        # Notion API에서 상세 정보 조회
        notion_db = await notion_service.get_active_database(db_info)
        if not notion_db:
            return {"status": "error", "message": "Notion API에서 데이터베이스 정보를 가져오는데 실패했습니다."}
            
        return {"status": "success", "data": notion_db}
    except Exception as e:
        api_logger.error(f"활성화된 DB 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 완료
@router.get("/available")
async def get_available_databases(user_id: str = Depends(require_user), supabase: AsyncClient = Depends(get_supabase)):
    """학습 가능한 DB 목록 조회"""
    try:
        available_dbs = await list_all_learning_databases(supabase, user_id)
        return {"status": "success", "data": available_dbs}
    except Exception as e:
        api_logger.error(f"학습 가능한 DB 목록 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 완료
@router.get("/", response_model=List[DatabaseInfo])
async def list_databases(user_id: str = Depends(require_user), supabase: AsyncClient = Depends(get_supabase)):
    """모든 학습 DB 목록 조회"""
    try:
        databases = await list_all_learning_databases(supabase, user_id)
        return databases
    except Exception as e:
        api_logger.error(f"모든 학습 DB 목록 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 완료
@router.get("/{db_id}", response_model=DatabaseResponse)
async def get_database(db_id: str, user_id: str = Depends(require_user), notion_service: NotionService = Depends(get_notion_service)):
    """DB 정보 조회"""
    try:
        #db_key = await get_db_key(db_id, user_id)
        database = await notion_service.get_database(db_id)
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
async def create_database(db: DatabaseCreate, user_id: str = Depends(require_user), supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service)):
    """새로운 DB 생성"""
    try:
        #db_key = await get_db_key(db.title, user_id)
        database = await notion_service.create_database(db.title)
        # Supabase에 데이터베이스 정보 저장
        await insert_learning_database(
            db_id=database.db_id,
            title=db.title,
            parent_page_id=settings.NOTION_PARENT_PAGE_ID,
            supabase=supabase,
            user_id=user_id
        )
        return DatabaseResponse(
            status="success",
            data=database,
            message="DB 성공적으로 생성되었습니다."
        )
    except NotionAPIError as e:
        api_logger.error(f"DB 생성 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 완료
@router.put("/{db_id}", response_model=DatabaseResponse)
async def update_database(db_id: str, db_update: DatabaseUpdate, user_id: str = Depends(require_user), supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service)):
    """DB 정보 업데이트"""
    try:
        # 1. Notion API 업데이트
        #db_key = await get_db_key(db_id, user_id)
        notion_db = await notion_service.update_database(db_id, db_update)
        
        # 2. Supabase 업데이트
        update_data = db_update.dict()
        if update_data:
            db_info = await update_learning_database(db_id, update_data, supabase, user_id)
        else:
            db_info = await get_db_info_by_id(db_id, supabase, user_id)
            
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
                webhook_status=db_info.get("webhook_status", "inactive")
            ),
            message="데이터베이스 정보가 성공적으로 업데이트되었습니다."
        )
    except NotionAPIError as e:
        api_logger.error(f"DB 업데이트 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 완료
@router.post("/{db_id}/activate")
async def activate_database(db_id: str, user_id: str = Depends(require_user), supabase: AsyncClient = Depends(get_supabase)):
    """데이터베이스 활성화"""
    try:
        result = await update_learning_database_status(db_id, "used", supabase, user_id)
        if not result:
            raise HTTPException(status_code=404, detail="데이터베이스를 찾을 수 없습니다.")
        return {"status": "success", "message": "데이터베이스가 활성화되었습니다."}
    except Exception as e:
        api_logger.error(f"DB 활성화 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 완료
@router.post("/deactivate")
async def deactivate_all_databases(user_id: str = Depends(require_user), supabase: AsyncClient = Depends(get_supabase)):
    """활성화된 DB를 비활성화 상태로 변경합니다."""
    try:
        result = await update_learning_database_status(db_id=None, status="ready", supabase=supabase, user_id=user_id)
        if not result:
            raise HTTPException(404, "활성화된 데이터베이스가 없습니다.")
        return {"status":"success", "message":"모든 데이터베이스를 비활성화했습니다."}
    except Exception as e:
        api_logger.error(f"모든 DB 비활성화 실패: {str(e)}")
        raise HTTPException(500, str(e))

# 완료
@router.get("/pages/{page_id}/databases", response_model=List[DatabaseMetadata])
async def get_page_databases(page_id: str, user_id: str = Depends(require_user), notion_service: NotionService = Depends(get_notion_service)):
    """페이지 내의 데이터베이스 목록 조회"""
    try:
        #db_key = await get_db_key(page_id, user_id)
        databases = await notion_service.list_databases_in_page(page_id)
        return databases
    except Exception as e:
        api_logger.error(f"페이지 내의 데이터베이스 목록 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 

