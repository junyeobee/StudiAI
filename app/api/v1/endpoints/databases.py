"""
데이터베이스 관련 API 엔드포인트
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional, Dict, Any
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
    get_available_learning_databases,
    insert_learning_database,
    get_db_info_by_id
)
from app.core.config import settings
router = APIRouter()
notion_service = NotionService()

# 완료
@router.post("/", response_model=DatabaseResponse)
async def create_database(db: DatabaseCreate):
    """새로운 데이터베이스 생성"""
    try:
        database = await notion_service.create_database(db.title)
        # Supabase에 데이터베이스 정보 저장
        insert_learning_database(
            db_id=database.db_id,
            title=db.title,
            parent_page_id=settings.NOTION_PARENT_PAGE_ID
        )
        return DatabaseResponse(
            status="success",
            data=database,
            message="데이터베이스가 성공적으로 생성되었습니다."
        )
    except NotionAPIError as e:
        raise HTTPException(status_code=500, detail=str(e))

# 완료
@router.get("/{db_id}", response_model=DatabaseResponse)
async def get_database(db_id: str):
    """데이터베이스 정보 조회"""
    try:
        database = await notion_service.get_database(db_id)
        return DatabaseResponse(
            status="success",
            data=database,
            message="데이터베이스 정보를 성공적으로 조회했습니다."
        )
    except NotionAPIError as e:
        raise HTTPException(status_code=404, detail=str(e))

# 완료
@router.put("/{db_id}", response_model=DatabaseResponse)
async def update_database(db_id: str, db_update: DatabaseUpdate):
    """데이터베이스 정보 업데이트"""
    try:
        database = await notion_service.update_database(db_id, db_update)
        return DatabaseResponse(
            status="success",
            data=database,
            message="데이터베이스 정보가 성공적으로 업데이트되었습니다."
        )
    except NotionAPIError as e:
        raise HTTPException(status_code=500, detail=str(e))

# 완료
@router.get("/", response_model=List[DatabaseInfo])
async def list_databases():
    """모든 학습 데이터베이스 목록 조회"""
    try:
        databases = await list_all_learning_databases()
        return databases
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 완료
@router.post("/{db_id}/activate")
async def activate_database(db_id: str):
    """데이터베이스 활성화"""
    try:
        result = update_learning_database_status(db_id, "used")
        if not result:
            raise HTTPException(status_code=404, detail="데이터베이스를 찾을 수 없습니다.")
        return {"status": "success", "message": "데이터베이스가 활성화되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 완료
@router.post("/{db_id}/deactivate")
async def deactivate_database(db_id: str):
    """데이터베이스 비활성화"""
    try:
        result = update_learning_database_status(db_id, "ready")
        if not result:
            raise HTTPException(status_code=404, detail="데이터베이스를 찾을 수 없습니다.")
        return {"status": "success", "message": "데이터베이스가 비활성화되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 완료
@router.get("/databases/active")
async def get_active_database():
    """현재 활성화된 데이터베이스 조회"""
    try:
        active_db = await get_active_learning_database()
        if not active_db:
            return {"status": "none", "message": "활성화된 데이터베이스가 없습니다."}
        return {"status": "success", "data": active_db}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 완료
@router.get("/databases/available")
async def get_available_databases():
    """학습 가능한 데이터베이스 목록 조회"""
    try:
        available_dbs = await list_all_learning_databases()
        return {"status": "success", "data": available_dbs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 완료
@router.get("/pages/{page_id}/databases", response_model=List[DatabaseMetadata])
async def get_page_databases(page_id: str):
    """페이지 내의 데이터베이스 목록 조회"""
    try:
        databases = await notion_service.list_databases_in_page(page_id)
        return databases
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 