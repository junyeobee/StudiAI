"""
Notion API 연동 서비스
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import httpx
from app.core.config import settings
from app.core.exceptions import NotionAPIError
from app.utils.logger import notion_logger
from app.models.database import (
    DatabaseInfo, 
    DatabaseStatus,
    DatabaseUpdate,
    DatabaseMetadata
)
from app.models.learning import (
    LearningPageCreate,
    LearningPlan
)
from app.utils.retry import async_retry

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

    @async_retry(max_retries=3, delay=1.0, backoff=2.0)
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

    # 데이터베이스 생성
    async def create_database(self, title: str) -> str:
        """새로운 데이터베이스 생성"""
        data = {
            "parent": {"page_id": settings.NOTION_PARENT_PAGE_ID},
            "title": [{"text": {"content": title}}],
            "properties": {
                "학습 제목": {"title": {}},
                "날짜": {"date": {}},
                "진행 상태": {"select": {"options": [
                    {"name": "시작 전", "color": "gray"},
                    {"name": "진행중", "color": "blue"},
                    {"name": "완료", "color": "green"}
                ]}},
                "복습 여부": {"checkbox": {}}
            }
        }
        response = await self._make_request("POST", "databases", json=data)
        return DatabaseInfo(
            db_id=response["id"],
            title=title,
            parent_page_id=settings.NOTION_PARENT_PAGE_ID,
            status=DatabaseStatus.READY,
            last_used_date=datetime.now()
        )
    
    # 데이터베이스 정보 조회
    async def get_database(self, database_id: str) -> DatabaseInfo:
        """데이터베이스 정보 조회"""
        response = await self._make_request("GET", f"databases/{database_id}")
        
        return DatabaseInfo(
            db_id=response["id"],
            title=response["title"][0]["text"]["content"],
            parent_page_id=response["parent"]["page_id"],
            status=DatabaseStatus.READY,
            last_used_date=datetime.now(),
            webhook_id=None,
            webhook_status="inactive"
        )

    # 학습 계획 페이지 업데이트
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

    # 페이지 내용 조회
    async def get_page_content(self, page_id: str) -> Dict[str, Any]:
        """페이지 내용 조회"""
        return await self._make_request("GET", f"blocks/{page_id}/children")

    # 페이지에 새로운 블록 추가
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

    # 페이지에 연결된 데이터베이스 목록 조회
    async def list_databases_in_page(self, page_id: str) -> List[DatabaseMetadata]:
        """페이지에 연결된 데이터베이스 목록 조회"""
        try:
            resp = await self._make_request(
                "GET",
                f"blocks/{page_id}/children",
                params={"page_size": 100}
            )

            return [
                {"id": block["id"], "title": block["child_database"]["title"]}
                for block in resp.get("results", [])
                if block.get("type") == "child_database"
            ]
            
        except Exception as e:
            notion_logger.error(f"데이터베이스 목록 조회 실패: {str(e)}")
            raise NotionAPIError(f"데이터베이스 목록 조회 실패: {str(e)}") 
        
    # 활성화된 데이터베이스 조회
    async def get_active_database(self, db_info: dict) -> DatabaseInfo:
        """활성화된 데이터베이스 조회"""
        if not db_info:
            return None
            
        # Notion API에서 데이터베이스 정보 조회
        response = await self._make_request("GET", f"databases/{db_info['db_id']}")
        
        return DatabaseInfo(
            db_id=db_info["db_id"],
            title=response["title"][0]["text"]["content"],
            parent_page_id=response["parent"]["page_id"],
            status=db_info["status"],
            last_used_date=db_info.get("last_used_date", datetime.now()),
            webhook_id=db_info.get("webhook_id"),
            webhook_status=db_info.get("webhook_status", "inactive")
        )

    # 데이터베이스 정보 업데이트 (Notion API만)
    async def update_database(self, database_id: str, db_update: DatabaseUpdate) -> DatabaseInfo:
        """데이터베이스 정보 업데이트 (Notion API만)"""
        try:
            # Notion API에서 데이터베이스 정보 조회
            response = await self._make_request("GET", f"databases/{database_id}")
            
            # 제목 업데이트
            if db_update.title:
                await self._make_request(
                    "PATCH", 
                    f"databases/{database_id}",
                    json={"title": [{"text": {"content": db_update.title}}]}
                )
            
            return DatabaseInfo(
                db_id=response["id"],
                title=db_update.title or response["title"][0]["text"]["content"],
                parent_page_id=response["parent"]["page_id"],
                status=db_update.status or DatabaseStatus.READY,
                last_used_date=datetime.now(),
                webhook_id=None,
                webhook_status=db_update.webhook_status or "inactive"
            )
            
        except Exception as e:
            notion_logger.error(f"데이터베이스 업데이트 실패: {str(e)}")
            raise NotionAPIError(f"데이터베이스 업데이트 실패: {str(e)}")
        

    async def create_learning_page(self, database_id: str, plan: LearningPageCreate) -> tuple[str, str]:
        """
        • 페이지를 생성하고  
        • 학습 목표 · AI 요약 블록을 자동으로 채운 뒤  
        • (page_id, ai_block_id) 튜플을 반환
        """
        # 1) 페이지 skeleton 생성
        props = {
            "학습 제목": {"title": [{"text": {"content": plan.title}}]},
            "날짜":     {"date":  {"start": plan.date.isoformat()}},
            "진행 상태": {"select": {"name": plan.status.value}},
            "복습 여부": {"checkbox": plan.revisit}
        }
        page_resp = await self._make_request(
            "POST",
            "pages",
            json={"parent": {"database_id": database_id}, "properties": props}
        )
        page_id = page_resp["id"]

        # 2) 본문 블록 구성
        blocks: List[dict] = [
            # 학습 목표
            {
                "object":"block","type":"heading_2",
                "heading_2":{"rich_text":[{"type":"text","text":{"content":"🧠 학습 목표"}}]}
            },
            {
                "object":"block","type":"quote",
                "quote":{"rich_text":[{"type":"text","text":{"content":plan.goal_intro}}]}
            },
        ]
        for goal in plan.goals:
            blocks.append({
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": [{"type": "text", "text": {"content": goal}}],
                    "checked": False
                }
            })
        blocks.append({"object":"block","type":"divider","divider":{}})

        # 🤖 AI 요약
        blocks.extend([
            {
                "object":"block","type":"heading_2",
                "heading_2":{"rich_text":[{"type":"text","text":{"content":"🤖 AI 요약 내용"}}]}
            },
            {
                "object":"block","type":"quote",
                "quote":{"rich_text":[{"type":"text","text":{"content":"학습 요약 정리를 자동화하거나 수동으로 작성하는 공간입니다."}}]}
            },
            {
                "object":"block","type":"code",
                "code":{
                    "rich_text":[{"type":"text","text":{"content":plan.summary}}],
                    "language":"markdown"
                }
            }
        ])

        # 3) 한 번에 children append
        append_resp = await self._make_request(
            "PATCH",
            f"blocks/{page_id}/children",
            json={"children": blocks}
        )
        ai_block_id = append_resp["results"][-1]["id"]  # 마지막 code 블록 ID

        return page_id, ai_block_id
    

    async def list_all_pages(self, database_id: str) -> List[Dict[str, Any]]:
        """
        주어진 Notion 데이터베이스의 모든 행(row) 페이지를 반환.
        반환값 예시:
        [
          {
            "page_id": "xxxxxxxx",
            "title": "컴포넌트 기본",
            "date":  "2025-04-30",
            "status": "진행중",
            "revisit": False
          },
          ...
        ]
        """
        has_more = True
        next_cursor = None
        pages: List[Dict[str, Any]] = []

        while has_more:
            body = {"start_cursor": next_cursor} if next_cursor else {}
            resp = await self._make_request(
                "POST",
                f"databases/{database_id}/query",
                json=body
            )
            for row in resp["results"]:
                props = row["properties"]
                pages.append({
                    "page_id": row["id"],
                    "title": props["학습 제목"]["title"][0]["text"]["content"] if props["학습 제목"]["title"] else "(제목 없음)",
                    "date":  props["날짜"]["date"]["start"] if props["날짜"]["date"] else None,
                    "status": props["진행 상태"]["select"]["name"] if props["진행 상태"]["select"] else "(상태 없음)",
                    "revisit": props["복습 여부"]["checkbox"] if props["복습 여부"]["checkbox"] else False
                })
            has_more = resp.get("has_more", False)
            next_cursor = resp.get("next_cursor")
            print(pages)
        return pages