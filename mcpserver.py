from typing import Any, List, Dict
import httpx
from mcp.server.fastmcp import FastMCP

# FastMCP 서버 초기화
mcp = FastMCP("studyai")

# StudyAI API 서버 주소
STUDYAI_API = "https://exit-land-nyc-exceptional.trycloudflare.com"

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

# 서버 실행
if __name__ == "__main__":
    mcp.run(transport='stdio')