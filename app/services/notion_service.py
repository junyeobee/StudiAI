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
    LearningPagesRequest
)
from app.utils.retry import async_retry

class NotionService:
    def __init__(self, token: str):
        self.api_key = token
        self.api_version = settings.NOTION_API_VERSION
        self.base_url = "https://api.notion.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": self.api_version,
            "Content-Type": "application/json"
        }
    # 노션 API 요청 공통 메서드
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
            # 요청 바디와 Notion 응답을 함께 로깅합니다.
            body = kwargs.get("json") or kwargs.get("params")
            status = e.response.status_code if e.response is not None else None
            text = e.response.text if e.response is not None else str(e)
            notion_logger.error(
                f"⛔ Notion API 오류:\n"
                f"   ▶ Method: {method}\n"
                f"   ▶ URL   : {url}\n"
                f"   ▶ Body  : {body}\n"
                f"   ▶ Status: {status}\n"
                f"   ▶ Error : {text}"
            )
            raise NotionAPIError(f"API 요청 실패: {text}")
        
    
    async def get_workspace_top_pages(self) -> List[Dict]:
        """사용자 워크스페이스의 최상위 페이지 반환"""
        payload = {
            "filter": {
                "value": "page",
                "property": "object"
            },
            "sort": {
                "direction": "descending",
                "timestamp": "last_edited_time"
            }
        }
        
        response = await self._make_request("POST", "search", json=payload)
        results = response.get("results", [])
        
        # 최상위 페이지만 필터링 (parent.type이 workspace인 경우)
        top_pages = [
            {
                "id": page["id"],
                "title": page["properties"]["title"]["title"][0]["plain_text"] 
                        if page.get("properties", {}).get("title", {}).get("title") 
                        else "Untitled",
                "url": page["url"],
                "last_edited": page["last_edited_time"]
            }
            for page in results
            if page.get("parent", {}).get("type") == "workspace"
        ]
        
        return top_pages


    # 데이터베이스 생성
    async def create_database(self, title: str, parent_page_id: str) -> str:
        """새로운 데이터베이스 생성"""
        data = {
            "parent": {"page_id": parent_page_id},
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
            parent_page_id=parent_page_id,
            status=DatabaseStatus.READY,
            last_used_date=datetime.now()
        )
    # 데이터베이스 정보 조회
    async def get_database(self, database_id: str, workspace_id: str) -> DatabaseInfo:
        """데이터베이스 정보 조회"""
        response = await self._make_request("GET", f"databases/{database_id}")
        
        return DatabaseInfo(
            db_id=response["id"],
            title=response["title"][0]["text"]["content"],
            parent_page_id=response["parent"]["page_id"],
            status=DatabaseStatus.READY,
            last_used_date=datetime.now(),
            webhook_id=None,
            webhook_status="inactive",
            workspace_id=workspace_id
        )

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
            webhook_status=db_info.get("webhook_status", "inactive"),
            workspace_id=db_info.get("workspace_id")
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
        
    # 학습 페이지 생성
    async def create_learning_page(self, database_id: str, plan: LearningPageCreate) -> tuple[str, str]:
        """
        - 데이터 베이스에 페이지(row)를 생성하고 학습 목표, 학습 내용, AI 분석 결과 템플릿 추가
        - (page_id, ai_analysis_log_page_id) 튜플을 반환
        """
        # 1) 페이지 속성
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
            # 🧠 학습 목표
            {
                "object":"block","type":"heading_2",
                "heading_2":{"rich_text":[{"type":"text","text":{"content":"🧠 학습 목표"}}]}
            },
            {
                "object":"block","type":"quote",
                "quote":{"rich_text":[{"type":"text","text":{"content":plan.goal_intro}}]}
            },
        ]
        
        # 학습 목표 to-do 추가
        for goal in plan.goals:
            blocks.append({
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": [{"type": "text", "text": {"content": goal}}],
                    "checked": False
                }
            })
        
        # 구분선
        blocks.append({"object":"block","type":"divider","divider":{}})

        # 📝 학습 내용
        blocks.extend([
            {
                "object":"block","type":"heading_2",
                "heading_2":{"rich_text":[{"type":"text","text":{"content":"📝 학습 내용"}}]}
            },
            {
                "object":"block","type":"quote",
                "quote":{"rich_text":[{"type":"text","text":{"content":"학습한 내용을 정리하는 공간입니다."}}]}
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": ""}}]
                }
            }
        ])
        
        # 구분선
        blocks.append({"object":"block","type":"divider","divider":{}})

        # 🤖 AI 분석 결과
        blocks.extend([
            {
                "object":"block","type":"heading_2",
                "heading_2":{"rich_text":[{"type":"text","text":{"content":"🤖 AI 분석 결과"}}]}
            },
            {
                "object":"block","type":"quote",
                "quote":{"rich_text":[{"type":"text","text":{"content":"MCP 요청과 커밋 분석 결과가 저장되는 공간입니다."}}]}
            }
        ])

        # 3) 모든 블록들을 한 번에 페이지에 추가
        append_resp = await self._make_request(
            "PATCH",
            f"blocks/{page_id}/children",
            json={"children": blocks}
        )
        if not append_resp :
            raise NotionAPIError(f"블록 추가 실패: {append_resp}")

        # 4) 📄 종합 분석 로그 페이지를 별도로 생성
        ai_analysis_page_props = {
            "parent": {"page_id": page_id},
            "properties": {
                "title": {
                    "title": [{"text": {"content": "Commit 분석 로그"}}]
                }
            }
        }
        ai_page_resp = await self._make_request(
            "POST",
            "pages",
            json=ai_analysis_page_props
        )
        ai_analysis_log_page_id = ai_page_resp["id"]

        # 5) 마크다운을 노션 블록으로 변환하여 메인 페이지에 직접 추가
        from app.utils.notion_utils import markdown_to_notion_blocks
        summary_blocks = markdown_to_notion_blocks(plan.summary)
        
        await self._make_request(
            "PATCH",
            f"blocks/{page_id}/children",
            json={"children": summary_blocks}
        )

        # 6) 종합 분석 로그 페이지에는 기본 안내 내용만 추가
        log_blocks = [
            {
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": "이 페이지는 커밋된 코드를 분석한 결과가 토글로 저장되는 공간입니다."}
                        }
                    ]
                }
            },
            {
                "object": "block",
                "type": "divider",
                "divider": {}
            }
        ]
        
        await self._make_request(
            "PATCH",
            f"blocks/{ai_analysis_log_page_id}/children",
            json={"children": log_blocks}
        )

        return page_id, ai_analysis_log_page_id
    
    # 데이터베이스 내 모든 페이지 조회
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
    
    # 페이지 속성 업데이트
    async def update_page_properties(self, page_id: str, props: Dict[str, Any]) -> None:
        """
        Notion 페이지의 속성(properties)만 업데이트합니다.
        """
        if not props:
            return
        await self._make_request(
            "PATCH",
            f"pages/{page_id}",
            json={"properties": props}
        )

    # 학습 목표 섹션 업데이트
    async def update_goal_section(self,page_id: str, goal_intro: Optional[str] = None, goals: Optional[List[str]] = None) -> None:
        """
        학습 목표 섹션(quote, to_do) 업데이트
        """
        # 1. 모든 블록 조회
        resp = await self._make_request(
            "GET",
            f"blocks/{page_id}/children",
            params={"page_size": 100}
        )
        blocks = resp.get("results", [])

        # 2. 목표 섹션 헤더 위치 찾기
        start_idx = None
        quote_block = None
        todo_blocks = []
        print(f'blocks: {blocks}')
        for idx, block in enumerate(blocks):
            if block.get("type") == "heading_2" and "🧠 학습 목표" in block["heading_2"]["rich_text"][0]["text"]["content"]:
                start_idx = idx
                continue
            if start_idx is not None:
                if block.get("type") == "quote":
                    quote_block = block
                elif block.get("type") == "to_do":
                    todo_blocks.append(block)
                elif block.get("type") == "heading_2":
                    break

        # 3. quote 업데이트
        if goal_intro is not None and quote_block:
            await self._make_request(
                "PATCH",
                f"blocks/{quote_block['id']}",
                json={
                    "quote": {"rich_text": [{"type": "text", "text": {"content": goal_intro}}]}
                }
            )

        # 4. to_do 업데이트
        if goals is not None:
            # 기존 to_do 삭제
            print(f'todo_blocks: {todo_blocks}')
            for block in todo_blocks:
                print(f'block: {block}')
                await self._make_request("DELETE", f"blocks/{block['id']}")
            
            new_todos = []
            for goal in goals:
                new_todos.append({
                    "object": "block",
                    "type": "to_do",
                    "to_do": {
                        "rich_text": [{"type": "text", "text": {"content": goal}}],
                        "checked": False
                    }
                })
            payload = {
                "children": new_todos,
                "after" : quote_block['id']
            }
            await self._make_request(
                "PATCH",
                f"blocks/{page_id}/children",
                json=payload
            )

    # 요약 페이지 업데이트
    async def update_ai_summary_by_page(self, page_id: str, summary: str) -> None:
        """
        AI 요약 페이지 ID를 받아서 해당 페이지의 코드 블록 업데이트
        """
        # 페이지 내 모든 블록 조회
        resp = await self._make_request(
            "GET",
            f"blocks/{page_id}/children",
            params={"page_size": 100}
        )
        blocks = resp.get("results", [])
        
        # 코드 블록 찾기
        code_block = None
        for block in blocks:
            if block.get("type") == "code":
                code_block = block
                break
        
        if code_block:
            # 기존 코드 블록 업데이트
            await self._make_request(
                "PATCH",
                f"blocks/{code_block['id']}",
                json={
                    "code": {
                        "rich_text": [{"type": "text", "text": {"content": summary}}],
                        "language": "markdown"
                    }
                }
            )
        else:
            # 코드 블록이 없으면 새로 추가
            new_block = {
                "object": "block",
                "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": summary}}],
                    "language": "markdown"
                }
            }
            await self._make_request(
                "PATCH",
                f"blocks/{page_id}/children",
                json={"children": [new_block]}
            )

    # 학습 페이지 종합 업데이트
    async def update_learning_page_comprehensive(self, ai_page_id: str, page_id: str, props: Optional[Dict[str, Any]] = None, goal_intro: Optional[str] = None, goals: Optional[List[str]] = None, summary: Optional[str] = None) -> None:
        """
        page_id 받아서 각 속성마다 존재한다면 업데이트
        1. 속성 업데이트
        2. 목표 섹션 업데이트
        3. 요약 페이지 업데이트
        """
        # 1. 속성 업데이트
        if props:
            await self.update_page_properties(page_id, props)

        # 2. 목표 섹션
        if goal_intro is not None or goals is not None:
            await self.update_goal_section(page_id, goal_intro, goals)

        # 3. 요약 페이지
        if ai_page_id is not None and summary is not None:
            await self.update_ai_summary_by_page(ai_page_id, summary)


    # 페이지 메타 및 블록 조회
    async def get_page_content(self, page_id: str) -> Dict[str, Any]:
        blocks, cursor = [], None
        while True:
            resp = await self._make_request(
                "GET", f"blocks/{page_id}/children",
                #dict unpacking -> cursor 있으면 추가, 없으면 빈 딕셔너리
                params={"page_size": 100, **({"start_cursor": cursor} if cursor else {})}
            )
            blocks.extend(resp["results"])
            if not resp.get("has_more"):
                break
            cursor = resp["next_cursor"]
        return {"blocks": blocks}
    
    # 페이지 삭제
    async def delete_page(self, page_id: str) -> None:
        """
        페이지 삭제
        """
        await self._make_request("PATCH", f"pages/{page_id}", json={"archived": True})
        