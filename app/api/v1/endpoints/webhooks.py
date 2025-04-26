"""
웹훅 관련 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Optional, Dict, Any
from app.services.webhook_service import WebhookService
from app.models.webhook import (
    WebhookInfo,
    WebhookCreate,
    WebhookUpdate,
    WebhookResponse,
    WebhookEvent
)
from app.core.exceptions import WebhookError
from app.utils.logger import webhook_logger
from pydantic import BaseModel
from supa import (
    update_webhook_info,
    get_webhook_info_by_db_id,
    verify_all_webhooks,
    retry_failed_webhook_operations,
    get_failed_webhook_operations,
    update_webhook_operation_status
)

router = APIRouter()
webhook_service = WebhookService()

class WebhookInfo(BaseModel):
    db_id: str
    webhook_id: Optional[str] = None
    webhook_status: str = "inactive"

class WebhookOperation(BaseModel):
    db_id: str
    operation_type: str
    webhook_id: Optional[str] = None
    status: str = "pending"
    error_message: Optional[str] = None

@router.post("/", response_model=WebhookResponse)
async def create_webhook(webhook: WebhookCreate):
    """새로운 웹훅 생성"""
    try:
        webhook_info = await webhook_service.create_webhook(webhook.db_id)
        return WebhookResponse(
            status="success",
            data=webhook_info,
            message="웹훅이 성공적으로 생성되었습니다."
        )
    except WebhookError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{db_id}")
async def delete_webhook(db_id: str):
    """웹훅 삭제"""
    try:
        await webhook_service.delete_webhook(db_id)
        return WebhookResponse(
            status="success",
            message="웹훅이 성공적으로 삭제되었습니다."
        )
    except WebhookError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{db_id}", response_model=WebhookResponse)
async def get_webhook(db_id: str):
    """웹훅 정보 조회"""
    try:
        webhook_info = webhook_service.get_webhook_info(db_id)
        if not webhook_info:
            raise HTTPException(status_code=404, detail="웹훅을 찾을 수 없습니다.")
        
        return WebhookResponse(
            status="success",
            data=webhook_info,
            message="웹훅 정보를 성공적으로 조회했습니다."
        )
    except WebhookError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{db_id}", response_model=WebhookResponse)
async def update_webhook(db_id: str, webhook_update: WebhookUpdate):
    """웹훅 상태 업데이트"""
    try:
        webhook_info = webhook_service.update_webhook_status(db_id, webhook_update.webhook_status)
        return WebhookResponse(
            status="success",
            data=webhook_info,
            message="웹훅 상태가 성공적으로 업데이트되었습니다."
        )
    except WebhookError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/events")
async def handle_webhook_event(event: WebhookEvent, background_tasks: BackgroundTasks):
    """웹훅 이벤트 처리"""
    try:
        # 이벤트 로깅을 백그라운드로 처리
        background_tasks.add_task(webhook_service.log_webhook_event, event.dict())
        
        return {
            "status": "success",
            "message": "웹훅 이벤트가 성공적으로 처리되었습니다."
        }
    except WebhookError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[WebhookInfo])
async def list_webhooks():
    """모든 웹훅 목록 조회"""
    try:
        # TODO: Supabase에서 웹훅 목록 조회 구현
        return []
    except WebhookError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/update")
def update_webhook(req: WebhookInfo):
    """웹훅 ID와 상태 업데이트"""
    result = update_webhook_info(req.db_id, req.webhook_id, req.webhook_status)
    
    if not result:
        raise HTTPException(status_code=404, detail="해당 ID의 데이터베이스를 찾을 수 없습니다.")
    
    return {
        "status": "updated",
        "db_id": req.db_id,
        "webhook_id": req.webhook_id
    }

@router.get("/{db_id}", response_model=WebhookInfo)
def get_webhook(db_id: str):
    """특정 DB ID에 대한 웹훅 정보를 반환"""
    webhook_info = get_webhook_info_by_db_id(db_id)
    
    if not webhook_info:
        return WebhookInfo(db_id=db_id)
    
    return WebhookInfo(
        db_id=db_id,
        webhook_id=webhook_info.get("webhook_id", ""),
        webhook_status=webhook_info.get("webhook_status", "inactive")
    )

@router.post("/verify")
async def verify_webhooks(background_tasks: BackgroundTasks):
    """모든 웹훅 상태 확인"""
    background_tasks.add_task(verify_all_webhooks)
    return {"status": "verification_started"}

@router.post("/retry")
async def retry_failed_operations(background_tasks: BackgroundTasks):
    """실패한 웹훅 작업 재시도"""
    background_tasks.add_task(retry_failed_webhook_operations)
    return {"status": "retry_started"}

@router.get("/failed")
def get_failed_operations():
    """실패한 웹훅 작업 목록 조회"""
    operations = get_failed_webhook_operations()
    return {"operations": operations}

@router.post("/monitor_all")
async def monitor_all(background_tasks: BackgroundTasks):
    """모든 DB에 대한 웹훅 모니터링 시작"""
    background_tasks.add_task(verify_all_webhooks)
    return {"status": "monitoring_started"}

@router.post("/unmonitor_all")
async def unmonitor_all(background_tasks: BackgroundTasks):
    """모든 DB에 대한 웹훅 모니터링 중지"""
    background_tasks.add_task(verify_all_webhooks)
    return {"status": "monitoring_stopped"} 