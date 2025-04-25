"""
데이터베이스 관련 API 엔드포인트
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from app.services.notion_service import NotionService
from app.models.database import (
    DatabaseInfo,
    DatabaseCreate,
    DatabaseUpdate,
    DatabaseResponse,
    DatabaseStatus
)
from app.core.exceptions import NotionAPIError, DatabaseError
from app.utils.logger import api_logger
from supa import list_all_learning_databases, update_learning_database_status

router = APIRouter()
notion_service = NotionService()

@router.post("/", response_model=DatabaseResponse)
async def create_database(db: DatabaseCreate):
    """새로운 데이터베이스 생성"""
    try:
        database = await notion_service.create_database(db.title, db.parent_page_id)
        return DatabaseResponse(
            status="success",
            data=database,
            message="데이터베이스가 성공적으로 생성되었습니다."
        )
    except NotionAPIError as e:
        raise HTTPException(status_code=500, detail=str(e))

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

@router.put("/{db_id}", response_model=DatabaseResponse)
async def update_database(db_id: str, db_update: DatabaseUpdate):
    """데이터베이스 정보 업데이트"""
    try:
        # 현재 데이터베이스 정보 조회
        current_db = await notion_service.get_database(db_id)
        
        # 업데이트할 필드만 선택
        update_data = db_update.dict(exclude_unset=True)
        
        # 데이터베이스 업데이트
        updated_db = DatabaseInfo(
            db_id=current_db.db_id,
            title=update_data.get("title", current_db.title),
            parent_page_id=current_db.parent_page_id,
            status=update_data.get("status", current_db.status),
            webhook_id=current_db.webhook_id,
            webhook_status=update_data.get("webhook_status", current_db.webhook_status),
            last_used_date=current_db.last_used_date
        )
        
        return DatabaseResponse(
            status="success",
            data=updated_db,
            message="데이터베이스 정보가 성공적으로 업데이트되었습니다."
        )
    except NotionAPIError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[DatabaseInfo])
async def list_databases():
    """모든 데이터베이스 목록 조회"""
    try:
        databases = list_all_learning_databases()
        return [
            DatabaseInfo(
                db_id=db.get("db_id", ""),
                title=db.get("title", ""),
                parent_page_id=db.get("parent_page_id", ""),
                status=db.get("status", DatabaseStatus.READY),
                webhook_id=db.get("webhook_id"),
                webhook_status=db.get("webhook_status", "inactive"),
                last_used_date=db.get("last_used_date")
            )
            for db in databases
        ]
    except Exception as e:
        api_logger.error(f"데이터베이스 목록 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{db_id}/activate")
async def activate_database(db_id: str):
    """데이터베이스를 활성화. 현재 활성화된 데이터베이스 비활성화 후 활성화"""
    try:
        # Notion에서 데이터베이스 정보 조회
        database = await notion_service.get_database(db_id)
        
        # 이미 활성화된 경우 처리
        if database.status == DatabaseStatus.USED:
            return DatabaseResponse(
                status="success",
                data=database,
                message="이미 활성화된 데이터베이스입니다."
            )
            
        # 상태 업데이트
        updated_db = update_learning_database_status(db_id, "used")
        
        if not updated_db:
            raise HTTPException(status_code=500, detail="데이터베이스 상태 업데이트 실패")
            
        # 기존 database 객체의 상태만 USED로 변경하여 반환
        return DatabaseResponse(
            status="success",
            data=DatabaseInfo(
                **database.model_dump(exclude={'status'}),
                status=DatabaseStatus.USED
            ),
            message="데이터베이스가 성공적으로 활성화되었습니다."
        )
    except NotionAPIError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{db_id}/deactivate")
async def deactivate_database(db_id: str):
    """데이터베이스 비활성화"""
    try:
        database = await notion_service.get_database(db_id)
        updated_db = DatabaseInfo(
            **database.dict(),
            status=DatabaseStatus.READY
        )
        
        return DatabaseResponse(
            status="success",
            data=updated_db,
            message="데이터베이스가 성공적으로 비활성화되었습니다."
        )
    except NotionAPIError as e:
        raise HTTPException(status_code=500, detail=str(e)) 