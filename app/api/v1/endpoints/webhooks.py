"""
웹훅 관련 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Optional
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

router = APIRouter()
webhook_service = WebhookService()

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