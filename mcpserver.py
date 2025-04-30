from typing import Any, List, Dict, Optional
import httpx
from mcp.server.fastmcp import FastMCP

# FastMCP 서버 초기화
mcp = FastMCP("studyai")

# StudyAI API 서버 주소
STUDYAI_API = "https://application-pencil-terminals-rights.trycloudflare.com"

WEBHOOK_CREATE_URL = "https://hook.eu2.make.com/39qh7m7j3ghar2r52i6w8aygn5n1526c"  # 웹훅 생성 시나리오 URL
WEBHOOK_DELETE_URL = "https://hook.eu1.make.com/hijklmn67890"  # 웹훅 삭제 시나리오 URL

@mcp.tool()
async def create_learning_pages(notion_db_id: str, plans: List[Dict[str, Any]]) -> str:
    """
    학습 DB(row) 안에 여러 학습 페이지를 한 번에 생성합니다. Args 예시는 다음과 같습니다. 형식에 맞게 작성해주세요.
    
    Args:
        notion_db_id: Notion 데이터베이스 ID (현재 선택된 학습 DB의 ID)
        plans: 학습 페이지 목록
            └─ 각 항목 예시는 다음과 같습니다. 사용자의 학습 목표 요구에 맞게 작성해주세요.
               {
                 "title": "컴포넌트 기본 개념",
                 "date": "2025-04-29T09:00:00Z" 날짜 형식은 ISO 8601 형식으로 작성해주세요.
                 "status": "시작 전", # ENUM 형식(시작 전, 진행중, 완료)
                 "revisit": false, #복습 여부
                 "goal": ["React 컴포넌트 개념 이해하기"],
                 "summary": "JSX·props·state에 집중한다"
                 "goal_intro": "컴포넌트의 기본 개념을 이해하고, 컴포넌트를 사용하는 방법 배우기"
               }
    Returns:
        성공/실패 메시지 문자열
    """
    url = f"{STUDYAI_API}/learning/pages/create"
    payload = {
        "notion_db_id": notion_db_id,
        "plans": plans
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=30.0)
            response.raise_for_status()
            created = response.json().get("total", 0)
            return f"학습 페이지 {created}개를 성공적으로 했습니다!"
        except Exception as e:
            return f"학습 페이지 생성 중 오류: {str(e)}"

@mcp.tool()
async def update_summary(page_id: str, summary: str) -> str:
    """페이지 요약 블록을 업데이트합니다.
    
    Args:
        page_id: Notion 페이지 ID
        summary: 업데이트할 요약 내용
    """
    url = f"{STUDYAI_API}/learning/pages/{page_id}/summary"
    payload = {
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
    url = f"{STUDYAI_API}/databases/active"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "none":
                return "현재 사용 중인 학습 데이터베이스가 없습니다. 새로운 데이터베이스를 생성하거나 기존 데이터베이스를 활성화해주세요."
            
            db = data.get("data", {})
            return f"""
                현재 사용 중인 학습 데이터베이스 정보:
                - 제목: {db.get('title')}
                - Notion DB ID: {db.get('db_id')}
                - 부모 페이지 ID: {db.get('parent_page_id')}
                """
        except Exception as e:
            return f"데이터베이스 조회 중 오류 발생: {str(e)}"
        
@mcp.tool()
async def list_learning_pages() -> str:
    """현재 학습 중인('used') 중인 db의 페이지 목록을 조회합니다."""
    url = f"{STUDYAI_API}/learning/pages/currentUsedDB"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            pages = data.get("pages", [])
            if not pages:
                return "현재 학습 중인 db에 페이지가 없습니다."
            
            page_list = "\n".join([f"- {page.get('title')} (ID: {page.get('page_id')})" for page in pages])
            return f"현재 학습 중인 db의 페이지 목록:\n{page_list}"
        except Exception as e:
            return f"페이지 목록 조회 중 오류 발생: {str(e)}"

@mcp.tool()
async def list_learning_databases() -> str:
    """사용 가능한 학습 데이터베이스 목록을 조회합니다."""
    url = f"{STUDYAI_API}/databases/available"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            dbs = data.get("data", [])
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
    url = f"{STUDYAI_API}/databases/pages/{parent_page_id}/databases"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            
            dbs = data
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
    url = f"{STUDYAI_API}/databases"
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
    url = f"{STUDYAI_API}/databases/{db_id}/activate"
    payload = {}
    
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
    url = f"{STUDYAI_API}/databases/{db_id}/deactivate"
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
    url = f"{STUDYAI_API}/webhooks/monitor/all"
    
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
    url = f"{STUDYAI_API}/webhooks/unmonitor/all"
    
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
    url = f"{STUDYAI_API}/webhooks/verify"
    
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
    url = f"{STUDYAI_API}/webhooks/retry"
    
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

@mcp.tool()
async def create_learning_database(title: str) -> str:
    """새 학습 데이터베이스를 생성.
    
    Args:
        title: 생성할 데이터베이스의 제목
    """
    url = f"{STUDYAI_API}/databases/"
    payload = {
        "title": title
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            return f"성공적으로 학습 데이터베이스가 생성되었습니다: {title}"
        except Exception as e:
            return f"데이터베이스 생성 중 오류 발생: {str(e)}"
        
# 페이지 업데이트
@mcp.tool()
async def update_learning_page(page_id: str,props: Optional[Dict[str, Any]] = None,goal_intro: Optional[str] = None,goals: Optional[List[str]] = None,summary: Optional[str] = None) -> str:
    """
    학습 페이지 부분 업데이트
    수정영역:(백틱 사용 금지)
    - props: 제목·날짜·상태·복습여부 등 속성
    - goal_intro/goals: 목표 섹션의 인용문과 to_do
    - summary: AI 요약 블록 내용
    
    예시:
    {
    "page_id": page_id,
    "props": {"학습 제목": {"title":[{"text":{"content":"새 제목"}}]}},
    "goal_intro": "목표 개요",
    "goals": ["목표1", "목표2"],
    "summary": {"summary": "AI 요약\\n줄바꿈시 이렇게 작성"}
    }
    """
    url = f"{STUDYAI_API}/learning/pages/{page_id}"
    payload: Dict[str, Any] = {}

    if props:
        payload['props'] = props

    if goal_intro is not None or goals is not None:
        content: Dict[str, Any] = {}
        if goal_intro is not None:
            content['goal_intro'] = goal_intro
        if goals is not None:
            content['goals'] = goals
        payload['content'] = content

    if summary is not None:
        payload['summary'] = summary

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.patch(url, json=payload, timeout=30.0)
            resp.raise_for_status()
            return "학습 페이지가 성공적으로 업데이트되었습니다."
        except Exception as e:
            return f"페이지 업데이트 중 오류 발생: {str(e)}"

# TODO: 30-75분 작업 - GitHub Webhook 엔드포인트 구현
# 1. FastAPI 라우터 추가
# 2. 시그니처 검증 코드 구현
# 3. payload 처리 로직 작성

# TODO: 75-120분 작업 - 통합 테스트 및 문서화
# 1. pytest-asyncio로 create_learning_database 테스트
# 2. /github_webhook 엔드포인트 테스트
# 3. 더미 push 이벤트로 200 응답 확인

# 서버 실행
if __name__ == "__main__":
    mcp.run(transport='stdio')
