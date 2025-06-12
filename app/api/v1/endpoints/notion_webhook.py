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
    # 헤더 및 바디 파싱
    headers = request.headers
    body = await request.body()
    api_logger.info(f"body: {headers}")
    # 시그니처 검증
    notion_signature = headers.get("x-notion-signature")
    if not notion_signature:
        # 시그니처 헤더 누락 (사용자/클라이언트 실수)
        api_logger.warning("시그니처 헤더가 없음")
        raise HTTPException(status_code=401, detail="Missing signature header")
        
    if not verify_signature(body, notion_signature):
        # 잘못된 시그니처 (사용자/클라이언트 실수)
        api_logger.warning(f"잘못된 시그니처: {notion_signature}")
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    api_logger.info("시그니처 검증 성공")
    
    payload = json.loads(body.decode())
    
    api_logger.info(f"웹훅 수신: {payload.get('type')} from workspace {payload.get('workspace_id')}")
    
    # 웹훅 핸들러에 위임 (커스텀 예외는 자동 전파됨)
    await webhook_handler.process_webhook_event(payload, supabase, redis_client)
    
    # 즉시 200 응답
    return {"status": "success"}
