from typing import Any, Callable, TypedDict
import logging, httpx
from strenum import StrEnum
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
from pydantic import ValidationError
#나중에 모델 -> dict로 변경할거임(배포용은 프로젝트 구조 없어서 모델 사용 불가)
from app.models.learning import LearningPagesRequest, PageUpdateRequest
from app.models.database import DatabaseCreate, DatabaseUpdate
from dotenv import load_dotenv
import os
import pathlib

# 프로젝트 루트 디렉토리 찾기
project_root = pathlib.Path(__file__).parent.absolute()
env_path = project_root / ".env"

# .env 파일 로드 시도
load_dotenv(dotenv_path=env_path)

# API 키 가져오기 (없으면 직접 설정할 수 있도록 None 반환)
api_key = os.getenv("STUDYAI_API_KEY")
if not api_key:
    logging.warning("STUDYAI_API_KEY 환경 변수를 찾을 수 없습니다. API 기능이 제한될 수 있습니다.")

# ───────────────────────기본 세팅 ───────────────────────
log = logging.getLogger("mcp")
logging.basicConfig(level=logging.INFO)

STUDYAI_API = "http://localhost:8000"

mcp = FastMCP(
    name="studyai",
    instructions=(
        "당신은 프로젝트/학습 관리 매니저입니다.\n"
        "노션 DB·웹훅을 관리합니다.\n"
        "모든 툴 호출은 params.payload 키를 포함해야 합니다."
    )
)

# ─────────────────────── 모델 & 헬퍼 ───────────────────────
class Route(TypedDict):
    method: str
    path: Callable[[dict[str, Any]], str]
    needs_json: bool

def _const(s: str) -> Callable[[dict[str, Any]], str]:
    """상수 경로 람다 래퍼"""
    return lambda _p: s

class Group(StrEnum):
    PAGE = "learning/pages"
    DB = "databases"
    WEB = "webhooks"
    NOTION_SETTINGS = "notion_settings"
    AUTH = "auth"

# 각 endpoint에 대한 Action Map
ACTION_MAP: dict[Group, dict[str, Route]] = {
    Group.PAGE: {
        "list": {"method":"GET", "path":lambda p:f"?db_id={p['db_id']}" if p.get("db_id") else "?current=true", "needs_json":False},
        "create": {"method":"POST", "path":_const("/create"), "needs_json":True},
        "update": {"method":"PATCH", "path":lambda p:f"/{p['page_id']}", "needs_json":True},
        "delete": {"method":"DELETE", "path":lambda p:f"/{p['page_id']}", "needs_json":False},
        "get": {"method":"GET", "path":lambda p:f"/{p['page_id']}/content", "needs_json":False},
    },
    Group.DB: {
        "list": {"method":"GET", "path":_const("/available"), "needs_json":False},
        "current": {"method":"GET", "path":_const("/active"), "needs_json":False},
        "create": {"method":"POST", "path":_const("/"), "needs_json":True},
        "activate": {"method":"POST", "path":lambda p:f"/{p['db_id']}/activate", "needs_json":False},
        "deactivate": {"method":"POST", "path":_const("/deactivate"), "needs_json":False},
        "update": {"method":"PATCH", "path":lambda p:f"/{p['db_id']}", "needs_json":True},
    },
    Group.WEB: {
        "start": {"method":"POST", "path":_const("/monitor/all"), "needs_json":False},
        "stop": {"method":"POST", "path":_const("/unmonitor/all"), "needs_json":False},
        "verify": {"method":"POST", "path":_const("/verify"), "needs_json":False},
        "retry": {"method":"POST", "path":_const("/retry"), "needs_json":False},
    },
    Group.NOTION_SETTINGS: {
        "workspaces": {"method":"GET", "path":_const("/workspaces"), "needs_json":False},
        "set_active_workspace": {"method":"POST", "path":_const("/workspaces/active"), "needs_json":True},
        "top_pages": {"method":"GET", "path":_const("/top-pages"), "needs_json":False},
        "set_top_page": {"method":"GET", "path":_const("/set-top-page"), "needs_json":False},
        "get_top_page": {"method":"GET", "path":_const("/get-top-page"), "needs_json":False},
    },
    Group.AUTH :{
        "get_token" : {"method":"GET", "path":lambda p:f"/oauth/{p['provider']}", "needs_json":False},
    }
}

PAYLOAD_MODEL = {
    (Group.PAGE, "create"): LearningPagesRequest,
    (Group.PAGE, "update"): PageUpdateRequest,
    (Group.DB, "create"): DatabaseCreate,
    (Group.DB, "update"): DatabaseUpdate,
}

EXAMPLE_MAP: dict[str, str] = {
    # DB 생성
    "database_tool.create": (
        "필수: title\n"
        "{\"payload\":{\"title\":\"학습 제목\"}}\n"
    ),

    # 페이지 수정
    "page_tool.update": (
        "필수: page_id | payload.props[title,date,status,revisit],payload.content[goal_intro,goals],payload.summary[summary]\n"
        "{\"payload\":{\"page_id\":\"\",\"props\":{\"title\":\"새 제목\",\"date\":\"2025-05-06T00:00:00Z\",\"status\":\"진행중\",\"revisit\":true},\"content\":{\"goal_intro\":\"수정된 목표 소개\",\"goals\":[\"새 목표1\",\"새 목표2\"]},\"summary\":{\"summary\":\"마크다운 형식으로 작성 (한 라인에 하나의 요소만)\\n예시:내용...\\n예시)#내용...\\n>내용...\\n\"}}"
        "ai_summary는 수정이 아닌 추가입니다."
    ),

    # 페이지 생성
    "page_tool.create": (
        "필수: notion_db_id, plans[title,date,status,revisit,goal_intro,goals,summary]\n"
        "{\"payload\":{\"notion_db_id\":\"\",\"plans\":[{\"title\":\"학습 제목\",\"date\":\"2025-05-06T00:00:00Z\",\"status\":\"시작 전\",\"revisit\":false,\"goal_intro\":\"학습 목표 소개\",\"goals\":[\"목표1\",\"목표2\"],\"summary\":\"마크다운 형식으로 작성 (한 라인에 하나의 요소만)\\n예시:내용...\\n예시)#내용...\\n>내용...\\n\"}]}}"
    ),

    # DB 페이지 조회
    "page_tool.list" : (
        "params.db_id 파라미터 넣을 시 특정 DB 페이지 리스트 조회\n"
        "파라미터 none: current DB의 리스트 조회"
    ),

    # DB 페이지 삭제
    "page_tool.delete" : (
        "params.page_id 파라미터 넣을 시 특정 페이지 삭제"
    ),

    # DB 페이지 조회
    "page_tool.get" : (
        "params.page_id 파라미터 넣을 시 특정 페이지 조회"
    ),
    
    # 워크스페이스 목록 조회
    "notion_settings_tool.workspaces" : (
        "파라미터 불필요: 사용 가능한 노션 워크스페이스 목록 조회"
    ),
    
    # 활성 워크스페이스 설정
    "notion_settings_tool.set_active_workspace" : (
        "필수: workspace_id\n"
        "{\"payload\":{\"workspace_id\":\"워크스페이스_아이디\"}}"
    ),
    
    # 최상위 페이지 목록 조회
    "notion_settings_tool.top_pages" : (
        "파라미터 불필요: 현재 워크스페이스의 최상위 페이지 목록 조회"
    ),
    
    # 최상위 페이지 설정
    "notion_settings_tool.set_top_page" : (
        "params.page_id: 최상위 페이지 id"
    ),
    
    # 현재 최상위 페이지 조회
    "notion_settings_tool.get_top_page" : (
        "파라미터 불필요: 현재 설정된 최상위 페이지 조회"
    ),
    "auth_tool.get_token" : (
        "params.provider: notion | github_webhook | notion_webhook\n"
        "토큰 발급 링크 반환"
    ),
    
}
USER_GUIDE : dict[str, str] = {
    "default" : (
        "이 MCP는 학습/프로젝트 관리 매니저 입니다.\n"
        "현재 노션 DB·웹훅을 관리할 수 있습니다\n"
        "또한, 필요한 API키를 간편하게 발급받고, 관리할 수 있습니다.\n"
        "Github 웹훅은 커밋 이벤트 발생 시 커밋 내용을 요약하여 Notion 페이지에 추가합니다.\n"
        "자세한 내용을 알고싶다면, 각 항목을 호출하세요"
    ),
    "Auth" : (
        "API키를 관리합니다.\n"
        "Notion/Github의 토큰을 발급/삭제 할 수 있습니다.\n"
        "[토큰 발급]: API키를 발급합니다.\n"
        "[토큰 삭제]: API키를 삭제합니다."
    ),
    "Notion_Settings" : (
        "노션 설정을 관리합니다.\n"
        "지금 활성화된 워크스페이스에서 다음 작업을 진행할 수 있습니다:\n"
        "[워크스페이스 목록 조회]: 사용 가능한 노션 워크스페이스 목록 조회합니다.\n"
        "[워크스페이스 설정]: 활성화된 워크스페이스를 설정합니다.\n"
        "[최상위 페이지 설정]: 최상위 페이지를 설정합니다.\n"
        "[최상위 페이지 조회]: 최상위 페이지를 조회합니다."
    ),
    "Database" : (
        "학습 트래커 DB를 관리합니다.\n"
        "사용자의 노션 토큰이 유효하다면, 활성화된 Workspace에서 다음 작업을 진행할 수 있습니다:\n"
        "[데이터베이스 생성]: 새로운 학습 트래커 DB를 생성합니다.\n"
        "[학습 페이지 작성]: AI 요약을 포함한 페이지를 생성합니다.\n"
        "[현재 페이지 조회]: 최근 학습 중인 페이지 내용을 확인합니다.\n"
        "[DB 활성화 전환]: 다른 데이터베이스로 전환하여 컨텍스트를 바꿉니다."
    ),
    "Page" : (
        "학습 페이지를 관리합니다.\n"
        "지금 활성화된 워크스페이스에서 다음 작업을 진행할 수 있습니다:\n"
        "[학습 페이지 생성]: AI 요약을 포함한 페이지를 생성합니다.\n"
        "[학습 페이지 수정]: 페이지 내용을 수정합니다. summary 필드는 AI 분석 결과 섹션에 내용을 추가합니다.\n"
        "[학습 페이지 삭제]: 페이지를 삭제합니다.\n"
        "[학습 페이지 조회]: 페이지 내용을 확인합니다."
    ),
    "Webhook" : (
        "웹훅을 관리합니다.\n"
        "지금 활성화된 워크스페이스에서 다음 작업을 진행할 수 있습니다:\n"
        "[웹훅 시작]: 웹훅을 시작합니다.\n"
        "[웹훅 중지]: 웹훅을 중지합니다.\n"
        "[웹훅 확인]: 웹훅 상태를 확인합니다.\n"
        "[웹훅 재시도]: 웹훅을 재시도합니다."
    ),
}
ERROR_MSG = {
    400: "400 Bad Request",
    401: "401 Unauthorized",
    403: "403 Forbidden",
    404: "404 Not Found, ID 확인 필요",
    422: "422 Unprocessable: payload 형식을 확인",
    429: "429 Too Many Requests",
    500: "500 Internal Server Error",
}

#Http Client 싱글톤
_client: httpx.AsyncClient | None = None

async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client

# Payload 검증
def _get_payload(group: Group, action: str, params: dict) -> dict | None:
    spec = ACTION_MAP[group][action]
    if not spec["needs_json"]:
        return None

    raw_payload = params.get("payload")
    if raw_payload is None:
        raise ValueError(f"{action} helper툴을 호출해서 파라미터 형식을 확인")

    model_cls = PAYLOAD_MODEL.get((group, action))
    if model_cls is None:
        return raw_payload

    try:
        return model_cls.model_validate(raw_payload).model_dump(mode="json")
    except ValidationError as ve:
        raise ValueError(f"payload 검증 실패: {ve}") from ve

# 툴 디스패치
async def dispatch(group: Group, action: str, params: dict) -> str:
    spec = ACTION_MAP[group].get(action)
    if not spec:
        return f"{group.value} 지원되지 않는 action '{action}'"
    
    try:
        payload = _get_payload(group, action, params)
    except ValueError as e:
        return str(e)
    
    headers = {"Authorization": f"Bearer {api_key}"}
    
    if spec["method"] in ('POST', 'PATCH', 'DELETE', 'PUT'):
        if not params.get("confirm"):
            return "사용자 승인 필요, 승인 시 같은 요청에 params.confirm 포함, 취소 시 무시"

    path = spec["path"](params)
    url  = f"{STUDYAI_API}/{group.value}{path}"

    client = await get_client()
    log.debug("→ %s %s", spec["method"], url)

    try:
        res = await client.request(spec["method"], url, json=payload, headers=headers)
        res.raise_for_status()
        if res.headers.get("content-type", "").startswith("application/json"):
            return res.json()
        return "성공"

    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        return f"HTTP {code}: {ERROR_MSG.get(code, e.response.text)}"
    except Exception as e:
        return f"{group.value} {action} 실패: {e}"

# ─────────────────────── MCP 툴 ───────────────────────
@mcp.tool(description="Notion 페이지 관련 액션 처리 (list|create|update|delete|get)")
async def page_tool(action: str, params: dict[str, Any]) -> str:
    return await dispatch(Group.PAGE, action, params)

@mcp.tool(description="학습 DB 관련 액션 처리 (list|current|create|activate|deactivate|update)")
async def database_tool(action: str, params: dict[str, Any]) -> str:
    return await dispatch(Group.DB, action, params)

@mcp.tool(description="웹훅/모니터링 액션 처리 (start|stop|verify|retry)") 
async def webhook_tool(action: str, params: dict[str, Any]) -> str:
    return await dispatch(Group.WEB, action, params)

@mcp.tool(description="노션 설정 관련 액션 처리 (workspaces|set_active_workspace|top_pages|set_top_page|get_top_page)")
async def notion_settings_tool(action: str, params: dict[str, Any]) -> str:
    return await dispatch(Group.NOTION_SETTINGS, action, params)

@mcp.tool(description="토큰 발급 액션 처리 (get_token)")
async def auth_tool(action: str, params: dict[str, Any]) -> str:
    return await dispatch(Group.AUTH, action, params)

@mcp.tool(description="요청 예시(액션명.기능 -> 파라미터 형식 반환)")
def helper(action: str) -> str:
    examples = EXAMPLE_MAP
    return examples.get(action, "지원 안 함")

@mcp.tool(description="사용자 가이드 제공, params.action 파라미터 미입력시 default 가이드, 입력시(Databases|Page|Notion_Settings|Auth|Webhook) 해당 가이드 반환")
def user_guide(action: str = "default") -> str:
    return USER_GUIDE.get(action, "지원 안 함")

# ───────────────────────초기 가이드 prompt ───────────────────────
@mcp.prompt(name="Essential Guidelines", description="필수 지침 사항")
def essential_guidelines() -> list[base.Message]:
    guide = (
        "⚠️ 필수 준수 사항 - 반드시 따라야 합니다! ⚠️\n\n"
        "1. 모든 변경성 액션(create/update/delete)은 반드시:\n"
        "   - 사용자에게 \"실행할까요? 예/아니오\" 명확히 질문할 것\n"
        "   - '예'라는 응답을 받은 경우에만 dispatch() 호출\n"
        "   - '아니오'인 경우 즉시 중단하고 \"취소했습니다\" 메시지 반환\n\n"
        "2. 시스템 운영 필수 규칙:\n"
        "   - 툴 호출시 한번에 한 요청만 처리\n"
        "   - 사용자의 요청이 완전히 끝날 때까지 기다리고 처리\n"
        "   - 모든 생성 요청은 사용자의 구체적인 요구사항을 정확히 반영\n"
        "   - 어떤 경우에도 사용자 확인 없이 변경 작업 실행 금지\n\n"
        "이 지침을 위반할 경우 심각한 데이터 오류가 발생할 수 있으며,\n"
        "모든 시스템 작업은 위 규칙을 엄격히 준수해야 합니다."
    )
    return [
            base.Message(
            role="assistant",
            content=base.TextContent(type="text", text=guide)
        )
    ]
@mcp.prompt(name="Params Guide", description="툴 사용시 파라미터 형식 가이드")
def guidelines() -> list[base.Message]:
    guide = (
        "자세한 요청 예시는 helper(액션명.기능) 호출\n"
        "호출 규칙 요약\n"
        "**params.payload 필수**\n"
        "database_tool(create), page_tool(create), page_tool(update)\n"
        "- ISO-8601 형식으로 날짜 입력, 예시: 2025-05-06T00:00:00+09:00Z\n"
        "- summary 블럭은 마크다운 형식으로 작성, 예시: # 학습 제목\\n ## 학습 내용\\n 학습 내용 작성\\n ## 학습 내용\\n 학습 내용 작성\n"
        "- page_tool(update) : params.payload = PageUpdateRequest\n"
        "**payload 불필요**\n"
        "- page_tool(list|delete|get)\n"
        "- database_tool(list | current | activate | deactivate)\n"
        "- webhook_tool(start | stop | verify | retry)\n"
        "- 툴 호출시 한번에 한 요청만 처리합니다."
    )
    return [
        base.Message(
            role="user",
            content=base.TextContent(type="text", text=guide)
        )
    ]

# ─────────────────────── run ───────────────────────
if __name__ == "__main__":
    mcp.run(transport="stdio")
