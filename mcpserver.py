from typing import Any, List, Dict, Optional
import json, sys, logging
import httpx
from mcp.server.fastmcp import FastMCP

# FastMCP 서버 초기화
mcp = FastMCP("studyai")
logger = logging.getLogger("mcp.debug")
if not logger.handlers:
    h = logging.StreamHandler(sys.stderr)   # stderr → mcp.log
    h.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(h)
    logger.setLevel(logging.INFO)

# StudyAI API 서버 주소
STUDYAI_API = "https://ver-gentleman-ok-wound.trycloudflare.com"

WEBHOOK_CREATE_URL = "https://hook.eu2.make.com/39qh7m7j3ghar2r52i6w8aygn5n1526c"  # 웹훅 생성 시나리오 URL
WEBHOOK_DELETE_URL = "https://hook.eu1.make.com/hijklmn67890"  # 웹훅 삭제 시나리오 URL

# DisPathcer 요청 공통 메서드
async def _request(method: str, url: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        resp = await client.request(method, url, timeout=30.0, **kwargs)
        resp.raise_for_status()
        return resp

PAGE_MAP: dict[str, dict] = {
    # action : {method, path_fn, needs_json}
    "list": {"method": "GET", "path": lambda p: f"?db_id={p['db_id']}" if p.get("db_id") else "?current=true", "needs_json": False},
    "create": {"method": "POST", "path": "/create", "needs_json": True},
    "update": {"method": "PATCH", "path": lambda p: f"/{p['page_id']}", "needs_json": True},
    "delete": {"method": "DELETE", "path": lambda p: f"/{p['page_id']}", "needs_json": False},
    "get": {"method": "GET", "path": lambda p: f"/{p['page_id']}/content", "needs_json": False},
}

# Page Dispatcher
@mcp.tool()
async def page_tool(action: str, params: dict) -> str:
    """
    Notion 페이지 관리
    action = list | create | get | update | delete
    생성(create): payload:{{"notion_db_id": <str>, "plans": [LearningPageCreate]}}
    수정(update): payload:{PageUpdateRequest}
    삭제(delete): page_id 필수
    조회(get): None(활성화DB)|page_id(특정DB)
    자세한 스키마 → models/learning.py
    """
    spec = PAGE_MAP.get(action)
    if not spec:
        return "지원하지 않는 action입니다."

    raw_path = spec["path"] 
    path = raw_path(params) if callable(raw_path) else raw_path
    url = f"{STUDYAI_API}/learning/pages{path}"
    print(params.get("payload"))
    body = params.get("payload") if spec["needs_json"] else None

    try:
        r = await _request(spec["method"], url, json=body)

        # 성공 반환
        return r.json() if action in ("list", "get") else f"page {action} 성공"

    except httpx.HTTPStatusError as e:
        # 서버가 4xx/5xx 반환
        logger.info(json.dumps({
            "tool": "database_tool",
            "action": action,
            "url": url,
            "status": e.response.status_code,
            "payload": body,
            "resp_text": e.response.text
        }, ensure_ascii=False))
        if e.response.status_code == 422:
            return (
                "422 오류: payload 형식이 맞지 않습니다.\n"
                "필수 키 → notion_db_id, plans (LearningPagesRequest 참고)"+body
            )
        return f"HTTP {e.response.status_code}: {e.response.text}"

    except Exception as e:
        # 네트워크 오류·타임아웃 등
        return f"page {action} 호출 실패: {e}"

DB_MAP = {
    "list": {"method": "GET", "path": "/available"},
    "current": {"method": "GET", "path": "/active"},
    "create": {"method": "POST", "path": "/", "needs_json": True},
    "activate": {"method": "POST", "path": lambda p: f"/{p['db_id']}/activate", "needs_json": False},
    "deactivate": {"method": "POST", "path": "/deactivate", "needs_json": False},
    "update": {"method": "PATCH", "path": lambda p: f"/{p['db_id']}", "needs_json": True},
}
# DB Dispatcher
@mcp.tool()
async def database_tool(action: str, params: dict) -> str:
    """
    노션 DB 관리
    action = list | current | create | activate | deactivate | update
    생성(create) : payload:{{"title": "<DB 제목>"}}
    활성화(activate) : db_id 필수
    비활성화(deactivate) : db_id 필수, payload:{{"end_status": true|false}} 선택
    조회(list) : db_id 필수
    수정(update) : db_id 필수, payload:{{"title": "<변경 시 변경할 DB 제목>"}}
    자세한 스키마 → models/database.py
    """
    spec = DB_MAP.get(action)
    if not spec:
        return "지원하지 않는 action입니다."
    
    raw_path = spec["path"]
    path = raw_path(params) if callable(raw_path) else raw_path
    url = f"{STUDYAI_API}/databases{path}"

    print(params.get("payload"))
    body = params.get("payload") if spec.get("needs_json") else None

    try:
        res = await _request(spec["method"], url, json=body)
        return res.json() if action in ("list", "current") else f"database {action} 성공"

    except httpx.HTTPStatusError as e:
        #디버깅용(지우기)
        logger.info(json.dumps({
            "tool": "database_tool",
            "action": action,
            "url": url,
            "status": e.response.status_code,
            "payload": body,
            "resp_text": e.response.text
        }, ensure_ascii=False))
        if e.response.status_code == 422 and action == "create":
            return "422 오류: payload에 title 키가 필요합니다."
        if e.response.status_code == 404 and action in ("activate", "deactivate"):
            return f"404: db_id '{params.get('db_id')}'를 찾을 수 없습니다."
        return f"HTTP {e.response.status_code}: {e.response.text}"

    except Exception as e:
        return f"database {action} 호출 실패: {e}"

WEBHOOK_MAP = {
    "start": {"method": "POST", "path": "/monitor/all"},
    "stop": {"method": "POST", "path": "/unmonitor/all"},
    "verify": {"method": "POST", "path": "/verify"},
    "retry": {"method": "POST", "path": "/retry"},
}

# Webhook Dispatcher
@mcp.tool()
async def webhook_tool(action: str, params: dict) -> str:
    """
    웹훅/모니터링 관리
    action = start | stop | verify | retry
      start : 모든 DB 모니터링 시작
      stop : 모든 DB 모니터링 중지
      verify : 활성 웹훅 상태 점검
      retry : 실패한 웹훅 작업 재시도
    """
    spec = WEBHOOK_MAP.get(action)
    if not spec:
        return "지원하지 않는 action입니다."

    raw_path = spec["path"] 
    path = raw_path(params) if callable(raw_path) else raw_path
    url = f"{STUDYAI_API}/webhooks{path}"

    try:
        resp = await _request(spec["method"], url, json=params.get("payload"))

        # GET 형태는 상태 리포트 JSON, 나머지는 성공 메시지
        return resp.json() if spec["method"] == "GET" else f"webhook {action} 성공"

    except httpx.HTTPStatusError as e:
        return f"HTTP {e.response.status_code}: {e.response.text}"

    except Exception as e:
        return f"webhook {action} 호출 실패: {e}"

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
