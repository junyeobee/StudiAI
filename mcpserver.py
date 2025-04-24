from typing import Any, List, Dict
import httpx
from mcp.server.fastmcp import FastMCP

# FastMCP 서버 초기화
mcp = FastMCP("studyai")

# StudyAI API 서버 주소
STUDYAI_API = "https://met-available-instrumental-linda.trycloudflare.com"

WEBHOOK_CREATE_URL = "https://hook.eu2.make.com/39qh7m7j3ghar2r52i6w8aygn5n1526c"  # 웹훅 생성 시나리오 URL
WEBHOOK_DELETE_URL = "https://hook.eu1.make.com/hijklmn67890"  # 웹훅 삭제 시나리오 URL

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
        
@mcp.tool()
async def activate_learning_database(db_id: str) -> str:
    """학습 데이터베이스를 활성화하고 웹훅을 설정합니다.
    
    Args:
        db_id: 활성화할 Notion 데이터베이스 ID
    """
    # 1. DB 상태를 'used'로 설정
    status_url = f"{STUDYAI_API}/update_db_status"
    status_payload = {"db_id": db_id, "status": "used"}
    
    # 2. Make.com 웹훅 생성 트리거
    webhook_payload = {
        "action": "create_webhook",
        "db_id": db_id,
        "source": "mcp_activation"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            # DB 상태 업데이트
            status_response = await client.post(status_url, json=status_payload, timeout=30.0)
            status_response.raise_for_status()
            status_data = status_response.json()
            
            # 웹훅 생성 트리거
            webhook_response = await client.post(WEBHOOK_CREATE_URL, json=webhook_payload, timeout=30.0)
            webhook_response.raise_for_status()
            
            return f"'{status_data['title']}' 데이터베이스가 활성화되었으며 웹훅이 설정되었습니다."
        except Exception as e:
            return f"데이터베이스 활성화 중 오류 발생: {str(e)}"

@mcp.tool()
async def deactivate_learning_database(db_id: str, end_status: bool = False) -> str:
    """학습 데이터베이스를 비활성화하고 웹훅을 제거합니다.
    
    Args:
        db_id: 비활성화할 Notion 데이터베이스 ID
        end_status: True면 'end' 상태로, False면 'ready' 상태로 설정
    """
    # 1. DB 상태 변경
    status_url = f"{STUDYAI_API}/update_db_status"
    status_payload = {
        "db_id": db_id, 
        "status": "end" if end_status else "ready"
    }
    
    # 2. Make.com 웹훅 제거 트리거
    webhook_payload = {
        "action": "delete_webhook",
        "db_id": db_id,
        "source": "mcp_deactivation"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            # DB 상태 업데이트
            status_response = await client.post(status_url, json=status_payload, timeout=30.0)
            status_response.raise_for_status()
            status_data = status_response.json()
            
            # 웹훅 제거 트리거
            webhook_response = await client.post(WEBHOOK_DELETE_URL, json=webhook_payload, timeout=30.0)
            webhook_response.raise_for_status()
            
            new_status = "완료" if end_status else "대기"
            return f"'{status_data['title']}' 데이터베이스가 {new_status} 상태로 변경되었으며 웹훅이 제거되었습니다."
        except Exception as e:
            return f"데이터베이스 비활성화 중 오류 발생: {str(e)}"

@mcp.tool()
async def complete_learning_database(db_id: str) -> str:
    """학습 데이터베이스를 완료 상태로 변경합니다.
    
    Args:
        db_id: 완료할 Notion 데이터베이스 ID
    """
    return await deactivate_learning_database(db_id, True)

@mcp.tool()
async def list_databases_in_parent_page(parent_page_id: str) -> str:
    """최상위 페이지에 있는 데이터베이스 목록을 조회합니다.
    
    Args:
        parent_page_id: Notion 최상위 페이지 ID
    """
    url = f"{STUDYAI_API}/list_db_in_page?parent_page_id={parent_page_id}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            if "error" in data:
                return f"데이터베이스 조회 실패: {data['error']}"
            
            if not data or len(data) == 0:
                return "페이지에 데이터베이스가 없습니다."
            
            result = "페이지에 있는 데이터베이스 목록:"
            for db in data:
                result += f"\n- {db['title']} (ID: {db['id']})"
            
            return result
        except Exception as e:
            return f"데이터베이스 목록 조회 중 오류 발생: {str(e)}"

# 서버 실행
if __name__ == "__main__":
    mcp.run(transport='stdio')
