from typing import Any, List, Dict
import httpx
from mcp.server.fastmcp import FastMCP

# FastMCP 서버 초기화
mcp = FastMCP("studyai")

# StudyAI API 서버 주소
STUDYAI_API = "https://personnel-arena-const-meditation.trycloudflare.com"

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
async def list_databases_in_parent_page(parent_page_id: str) -> str:
    """부모 페이지 내의 모든 데이터베이스를 조회합니다.
    
    Args:
        parent_page_id: 부모 페이지의 Notion ID
    """
    url = f"{STUDYAI_API}/page_databases/{parent_page_id}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            dbs = data.get("databases", [])
            if not dbs:
                return "해당 페이지에서 데이터베이스를 찾을 수 없습니다."
            
            db_list = "\n".join([f"- {db.get('title')} (ID: {db.get('id')})" for db in dbs])
            return f"페이지 내 데이터베이스 목록:\n{db_list}"
        except Exception as e:
            return f"데이터베이스 목록 조회 중 오류 발생: {str(e)}"

@mcp.tool()
async def register_new_database(parent_page_id: str, db_id: str, title: str) -> str:
    """새로운 학습 데이터베이스를 등록합니다.
    
    Args:
        parent_page_id: 부모 페이지의 Notion ID
        db_id: 데이터베이스의 Notion ID
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
            return f"성공적으로 데이터베이스가 등록되었습니다: {title}"
        except Exception as e:
            return f"데이터베이스 등록 중 오류 발생: {str(e)}"

@mcp.tool()
async def activate_learning_database(db_id: str) -> str:
    """학습 데이터베이스를 활성화합니다.
    
    Args:
        db_id: 활성화할 데이터베이스의 Notion ID
    """
    url = f"{STUDYAI_API}/activate_database"
    payload = {"db_id": db_id}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=30.0)
            response.raise_for_status()
            return f"데이터베이스가 성공적으로 활성화되었습니다."
        except Exception as e:
            return f"데이터베이스 활성화 중 오류 발생: {str(e)}"

@mcp.tool()
async def deactivate_learning_database(db_id: str, end_status: bool = False) -> str:
    """학습 데이터베이스를 비활성화합니다.
    
    Args:
        db_id: 비활성화할 데이터베이스의 Notion ID
        end_status: 학습 완료 상태로 설정할지 여부
    """
    url = f"{STUDYAI_API}/deactivate_database/{db_id}"
    payload = {"end_status": end_status}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=30.0)
            response.raise_for_status()
            return f"데이터베이스가 성공적으로 비활성화되었습니다."
        except Exception as e:
            return f"데이터베이스 비활성화 중 오류 발생: {str(e)}"

@mcp.tool()
async def complete_learning_database(db_id: str) -> str:
    """학습 데이터베이스를 완료 상태로 설정합니다.
    
    Args:
        db_id: 완료 처리할 데이터베이스의 Notion ID
    """
    return await deactivate_learning_database(db_id, end_status=True)

@mcp.tool()
async def start_monitoring_all_databases() -> str:
    """모든 데이터베이스의 모니터링을 시작합니다."""
    url = f"{STUDYAI_API}/monitor_all"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            return f"""
                모니터링 시작 결과:
                - 총 데이터베이스: {data.get('total', 0)}
                - 성공: {data.get('success', 0)}
                - 스킵: {data.get('skipped', 0)}
                - 실패: {data.get('failed', 0)}
                """
        except Exception as e:
            return f"모니터링 시작 중 오류 발생: {str(e)}"

@mcp.tool()
async def stop_monitoring_all_databases() -> str:
    """모든 데이터베이스의 모니터링을 중지합니다."""
    url = f"{STUDYAI_API}/unmonitor_all"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            return f"""
                모니터링 중지 결과:
                - 총 데이터베이스: {data.get('total', 0)}
                - 성공: {data.get('success', 0)}
                - 실패: {data.get('failed', 0)}
                """
        except Exception as e:
            return f"모니터링 중지 중 오류 발생: {str(e)}"

@mcp.tool()
async def verify_database_monitoring() -> str:
    """모든 데이터베이스의 모니터링 상태를 검증합니다."""
    url = f"{STUDYAI_API}/verify_webhooks"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            return f"""
                모니터링 검증 결과:
                - 총 웹훅: {data.get('total', 0)}
                - 성공: {data.get('success', 0)}
                - 실패: {data.get('failed', 0)}
                """
        except Exception as e:
            return f"모니터링 검증 중 오류 발생: {str(e)}"

@mcp.tool()
async def retry_failed_monitoring_operations() -> str:
    """실패한 모니터링 작업을 재시도합니다."""
    url = f"{STUDYAI_API}/retry_failed_operations"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            return f"""
                재시도 결과:
                - 총 작업: {data.get('total', 0)}
                - 성공: {data.get('success', 0)}
                - 실패: {data.get('failed', 0)}
                """
        except Exception as e:
            return f"재시도 중 오류 발생: {str(e)}"

# 서버 실행
if __name__ == "__main__":
    mcp.run(transport='stdio')
