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
from app.services.supa import (
    update_webhook_info,
    get_webhook_info_by_db_id,
    verify_all_webhooks,
    retry_failed_webhook_operations,
    get_failed_webhook_operations,
    update_webhook_operation_status
)
from app.services.notion_service import NotionService

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

@router.get("/", response_model=List[WebhookInfo])
async def get_webhooks():
    """웹훅 목록 조회"""
    try:
        notion = NotionService()
        webhooks = await notion.get_webhooks()
        return webhooks
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{webhook_id}", response_model=WebhookInfo)
async def get_webhook(webhook_id: str):
    """특정 웹훅 정보 조회"""
    try:
        notion = NotionService()
        webhook = await notion.get_webhook(webhook_id)
        return webhook
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Webhook not found: {str(e)}")

@router.post("/", response_model=WebhookInfo)
async def create_webhook(webhook: WebhookCreate):
    """새로운 웹훅 생성"""
    try:
        notion = NotionService()
        new_webhook = await notion.create_webhook(webhook)
        return new_webhook
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{webhook_id}", response_model=WebhookInfo)
async def update_webhook(webhook_id: str, webhook: WebhookUpdate):
    """웹훅 정보 수정"""
    try:
        notion = NotionService()
        updated_webhook = await notion.update_webhook(webhook_id, webhook)
        return updated_webhook
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str):
    """웹훅 삭제"""
    try:
        notion = NotionService()
        await notion.delete_webhook(webhook_id)
        return {"message": "Webhook deleted successfully"}
    except Exception as e:
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