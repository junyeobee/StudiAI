from typing import Dict, Optional
from app.services.supa import get_webhook_info_by_db_id

class WebhookService:
    """웹훅 서비스 클래스"""
    
    @staticmethod
    async def get_webhook_info(db_id: str) -> Optional[Dict]:
        """웹훅 정보를 조회합니다."""
        return await get_webhook_info_by_db_id(db_id) 