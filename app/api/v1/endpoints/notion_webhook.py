from fastapi import APIRouter, Request, HTTPException
from app.utils.logger import api_logger
import hmac
import hashlib
import json

router = APIRouter()

@router.post("/")
async def handle_notion_webhook(request: Request):
    """Master Integration으로부터 웹훅 이벤트 수신"""
    try:
        # 헤더 및 바디 파싱
        headers = request.headers
        body = await request.body()
        payload = json.loads(body.decode())
        token = headers.get("X-Notion-Webhook-Secret")
        api_logger.info(f"웹훅 수신: {payload}")
        
        # 시그니처 검증 (선택적)
        # notion_signature = headers.get("X-Notion-Signature")
        # if not verify_signature(body, notion_signature):
        #     raise HTTPException(status_code=401, detail="Invalid signature")
        
        # workspace_id로 사용자 구분
        workspace_id = payload.get("workspace_id")
        event_type = payload.get("type")
        entity = payload.get("entity", {})
        
        api_logger.info(f"웹훅 수신: {event_type} from workspace {workspace_id}")
        
        # 이벤트 처리
        await process_webhook_event(payload)
        
        return {"status": "success"}
        
    except Exception as e:
        api_logger.error(f"웹훅 처리 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_webhook_event(payload: dict):
    """웹훅 이벤트 처리 로직"""
    workspace_id = payload.get("workspace_id")
    event_type = payload.get("type")
    entity = payload.get("entity", {})
    
    # workspace_id로 learning_databases 테이블에서 해당 사용자의 DB 확인
    # 이벤트 타입별 처리 로직
    
    if event_type == "page.deleted":
        # 페이지 삭제 처리
        pass
    elif event_type == "page.content_updated":
        # 페이지 업데이트 처리  
        pass
    elif event_type == "database.deleted":
        # 데이터베이스 삭제 처리
        pass
    
    # 처리 완료
    api_logger.info(f"이벤트 처리 완료: {event_type}")
