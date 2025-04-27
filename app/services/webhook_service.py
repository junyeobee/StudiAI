from typing import Dict, Optional
import httpx
from app.core.config import settings
from app.utils.logger import webhook_logger
from app.services.supa import (
    get_webhook_info_by_db_id,
    update_webhook_info,
    log_webhook_operation
)

class WebhookService:
    """웹훅 서비스 클래스"""
    
    @staticmethod
    async def create_webhook(db_id: str) -> Dict[str, str]:
        """웹훅을 생성합니다."""
        try:
            # Make.com 웹훅 생성 URL
            webhook_url = settings.WEBHOOK_CREATE_URL
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json={"db_id": db_id},
                    timeout=30.0
                )
                response.raise_for_status()
            
            # 웹훅 생성 성공 로그
            await log_webhook_operation(
                db_id,
                "create",
                "success",
                None,
                None
            )
            
            return {"status": "created"}
            
        except Exception as e:
            # 웹훅 생성 실패 로그
            await log_webhook_operation(
                db_id,
                "create",
                "failed",
                str(e),
                None
            )
            raise
    
    @staticmethod
    async def delete_webhook(db_id: str) -> Dict[str, str]:
        """웹훅을 삭제합니다."""
        webhook_id = None
        try:
            # 현재 웹훅 정보 가져오기
            webhook_info = await get_webhook_info_by_db_id(db_id)
            webhook_id = webhook_info.get("webhook_id") if webhook_info else None
            
            # Make.com 웹훅 삭제 URL
            webhook_url = settings.WEBHOOK_DELETE_URL
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json={"db_id": db_id},
                    timeout=30.0
                )
                response.raise_for_status()
            
            # 웹훅 삭제 성공 로그
            await log_webhook_operation(
                db_id,
                "delete",
                "success",
                None,
                webhook_id
            )
            
            return {"status": "deleted"}
            
        except Exception as e:
            # 웹훅 삭제 실패 로그
            await log_webhook_operation(
                db_id,
                "delete",
                "failed",
                str(e),
                webhook_id
            )
            raise
    
    @staticmethod
    async def get_webhook_info(db_id: str) -> Optional[Dict]:
        """웹훅 정보를 조회합니다."""
        return await get_webhook_info_by_db_id(db_id)
    
    @staticmethod
    async def update_webhook_status(db_id: str, webhook_id: str, status: str) -> bool:
        """웹훅 상태를 업데이트합니다."""
        return await update_webhook_info(db_id, webhook_id, status) 