from typing import Any, List, Dict
import httpx
from mcp.server.fastmcp import FastMCP

# FastMCP 서버 초기화
mcp = FastMCP("studyai")

# StudyAI API 서버 주소
STUDYAI_API = "https://threatened-frank-both-anonymous.trycloudflare.com"

@mcp.tool()
async def create_learning_plan(db_title: str, plans: List[Dict[str, Any]]) -> str:
    """학습 계획 페이지를 생성합니다.
    
    Args:
        db_title: 학습 데이터베이스 제목 (예: "React 학습 계획")
        plans: 생성할 학습 계획 목록 (각 계획은 title, goal_items, summary를 포함)
    """
    url = f"{STUDYAI_API}/create_page"
    payload = {
        "db_title": db_title,
        "plans": plans
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            return f"성공적으로 학습 계획이 생성되었습니다."
        except Exception as e:
            return f"학습 계획 생성 중 오류 발생: {str(e)}"

@mcp.tool()
async def update_summary(page_id: str, summary: str) -> str:
    """페이지 요약 블록을 업데이트합니다.
    
    Args:
        page_id: Notion 페이지 ID
        summary: 업데이트할 요약 내용
    """
    url = f"{STUDYAI_API}/fill_summary"
    payload = {
        "page_id": page_id,
        "summary": summary
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=30.0)
            response.raise_for_status()
            return "요약이 성공적으로 업데이트되었습니다."
        except Exception as e:
            return f"요약 업데이트 중 오류 발생: {str(e)}"
        
@mcp.tool()
async def get_current_learning_database() -> str:
    """현재 사용 중인 학습 데이터베이스를 조회합니다."""
    url = f"{STUDYAI_API}/active_database"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "none":
                return "현재 사용 중인 학습 데이터베이스가 없습니다. 새로운 데이터베이스를 생성하거나 기존 데이터베이스를 활성화해주세요."
            
            db = data.get("database", {})
            return f"""
                현재 사용 중인 학습 데이터베이스 정보:
                - 제목: {db.get('title')}
                - Notion DB ID: {db.get('db_id')}
                - 부모 페이지 ID: {db.get('parent_page_id')}
                """
        except Exception as e:
            return f"데이터베이스 조회 중 오류 발생: {str(e)}"

@mcp.tool()
async def list_learning_databases() -> str:
    """사용 가능한 학습 데이터베이스 목록을 조회합니다."""
    url = f"{STUDYAI_API}/available_databases"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            dbs = data.get("databases", [])
            if not dbs:
                return "사용 가능한 학습 데이터베이스가 없습니다. 새로운 데이터베이스를 생성해주세요."
            
            db_list = "\n".join([f"- {db.get('title')} (ID: {db.get('db_id')})" for db in dbs])
            return f"사용 가능한 학습 데이터베이스 목록:\n{db_list}"
        except Exception as e:
            return f"데이터베이스 목록 조회 중 오류 발생: {str(e)}"

@mcp.tool()
async def list_databases_in_parent_page(parent_page_id: str) -> str:
    """최상위 페이지에 있는 데이터베이스 목록을 조회합니다.
    
    Args:
        parent_page_id: Notion 최상위 페이지 ID
    """
    url = f"{STUDYAI_API}/page_databases/{parent_page_id}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            if "status" in data and data["status"] == "error":
                return f"데이터베이스 조회 중 오류 발생: {data.get('message')}"
            
            dbs = data.get("databases", [])
            if not dbs:
                return "해당 페이지에 데이터베이스가 없습니다."
            
            db_list = "\n".join([f"- {db.get('title')} (ID: {db.get('id')})" for db in dbs])
            return f"페이지에 있는 데이터베이스 목록:\n{db_list}"
        except Exception as e:
            return f"데이터베이스 목록 조회 중 오류 발생: {str(e)}"

@mcp.tool()
async def activate_learning_database(db_id: str) -> str:
    """학습 데이터베이스를 활성화합니다.
    
    Args:
        db_id: 활성화할 Notion 데이터베이스 ID
    """
    url = f"{STUDYAI_API}/activate_database"
    payload = {"db_id": db_id}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=30.0)
            response.raise_for_status()
            return f"학습 데이터베이스(ID: {db_id})가 성공적으로 활성화되었습니다."
        except Exception as e:
            return f"데이터베이스 활성화 중 오류 발생: {str(e)}"

@mcp.tool()
async def register_new_database(parent_page_id: str, db_id: str, title: str) -> str:
    """새로운 학습 데이터베이스를 등록합니다.
    
    Args:
        parent_page_id: Notion 부모 페이지 ID
        db_id: Notion 데이터베이스 ID
        title: 데이터베이스 제목
    """
    url = f"{STUDYAI_API}/register_database"
    payload = {
        "parent_page_id": parent_page_id,
        "db_id": db_id,
        "title": title
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=30.0)
            response.raise_for_status()
            return f"새로운 학습 데이터베이스 '{title}'이 성공적으로 등록되었습니다."
        except Exception as e:
            return f"데이터베이스 등록 중 오류 발생: {str(e)}"

# 서버 실행
if __name__ == "__main__":
    mcp.run(transport='stdio')
