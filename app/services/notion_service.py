"""
Notion API 연동 서비스
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import httpx
from app.config.settings import settings
from app.core.exceptions import NotionAPIError
from app.utils.logger import notion_logger
from app.models.database import DatabaseInfo, DatabaseStatus
from app.models.learning import LearningPlan, LearningStatus
from supa import get_db_info_by_id

class NotionService:
    def __init__(self):
        self.api_key = settings.NOTION_API_KEY
        self.api_version = settings.NOTION_API_VERSION
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": self.api_version,
            "Content-Type": "application/json"
        }

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Notion API 요청을 보내는 공통 메서드"""
        url = f"{self.base_url}/{endpoint}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(method, url, headers=self.headers, **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            notion_logger.error(f"Notion API 요청 실패: {str(e)}")
            raise NotionAPIError(f"API 요청 실패: {str(e)}")

    async def create_database(self, title: str, parent_page_id: str) -> DatabaseInfo:
        """새로운 데이터베이스 생성"""
        data = {
            "parent": {"page_id": parent_page_id},
            "title": [{"text": {"content": title}}],
            "properties": {
                "Title": {"title": {}},
                "Status": {"select": {}},
                "Priority": {"number": {}},
                "Tags": {"multi_select": {}},
                "Start Date": {"date": {}},
                "End Date": {"date": {}}
            }
        }
        
        response = await self._make_request("POST", "databases", json=data)
        return DatabaseInfo(
            db_id=response["id"],
            title=title,
            parent_page_id=parent_page_id,
            status=DatabaseStatus.READY,
            last_used_date=datetime.now()
        )

    async def get_database(self, database_id: str) -> DatabaseInfo:
        """데이터베이스 정보 조회"""
        response = await self._make_request("GET", f"databases/{database_id}")
        
        # Supabase에서 데이터베이스 상태 조회
        db_info = get_db_info_by_id(database_id)
        
        return DatabaseInfo(
            db_id=response["id"],
            title=response["title"][0]["text"]["content"],
            parent_page_id=response["parent"]["page_id"],
            status=db_info.get("status", DatabaseStatus.READY) if db_info else DatabaseStatus.READY,
            last_used_date=db_info.get("last_used_date", datetime.now()) if db_info else datetime.now(),
            webhook_id=db_info.get("webhook_id") if db_info else None,
            webhook_status=db_info.get("webhook_status", "inactive") if db_info else "inactive"
        )

    async def create_learning_page(self, database_id: str, plan: LearningPlan) -> str:
        """학습 계획 페이지 생성"""
        data = {
            "parent": {"database_id": database_id},
            "properties": {
                "Title": {
                    "title": [{"text": {"content": plan.title}}]
                },
                "Status": {
                    "select": {"name": plan.status.value}
                },
                "Priority": {
                    "number": plan.priority
                },
                "Tags": {
                    "multi_select": [{"name": tag} for tag in plan.tags]
                }
            }
        }
        
        if plan.start_date:
            data["properties"]["Start Date"] = {"date": {"start": plan.start_date.isoformat()}}
        if plan.end_date:
            data["properties"]["End Date"] = {"date": {"start": plan.end_date.isoformat()}}
        
        response = await self._make_request("POST", "pages", json=data)
        return response["id"]

    async def update_learning_page(self, page_id: str, plan: LearningPlan) -> None:
        """학습 계획 페이지 업데이트"""
        data = {
            "properties": {
                "Title": {
                    "title": [{"text": {"content": plan.title}}]
                },
                "Status": {
                    "select": {"name": plan.status.value}
                },
                "Priority": {
                    "number": plan.priority
                },
                "Tags": {
                    "multi_select": [{"name": tag} for tag in plan.tags]
                }
            }
        }
        
        if plan.start_date:
            data["properties"]["Start Date"] = {"date": {"start": plan.start_date.isoformat()}}
        if plan.end_date:
            data["properties"]["End Date"] = {"date": {"start": plan.end_date.isoformat()}}
        
        await self._make_request("PATCH", f"pages/{page_id}", json=data)

    async def get_page_content(self, page_id: str) -> Dict[str, Any]:
        """페이지 내용 조회"""
        return await self._make_request("GET", f"blocks/{page_id}/children")

    async def append_block(self, page_id: str, block_type: str, content: str) -> None:
        """페이지에 새로운 블록 추가"""
        data = {
            "children": [{
                "object": "block",
                "type": block_type,
                block_type: {
                    "rich_text": [{"text": {"content": content}}]
                }
            }]
        }
        await self._make_request("PATCH", f"blocks/{page_id}/children", json=data) 