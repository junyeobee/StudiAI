from typing import Any, Callable, TypedDict
import logging, httpx
from strenum import StrEnum
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
from pydantic import ValidationError

from app.models.learning import LearningPagesRequest, PageUpdateRequest
from app.models.database import DatabaseCreate, DatabaseUpdate

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
        "{\"payload\":{\"title\":\"학습 제목\"}}"
    ),

    # 페이지 수정
    "page_tool.update": (
        "필수: page_id, payload[title,date,status,revisit,goal_intro,goals,summary]\n"
        "{\"payload\":{\"page_id\":\"\",\"title\":\"새 제목\",\"date\":\"2025-05-06T00:00:00Z\",\"status\":\"진행중\",\"revisit\":true,\"goal_intro\":\"수정된 목표 소개\",\"goals\":[\"새 목표1\",\"새 목표2\"],\"summary\":\"수정된 요약\"}}"
    ),

    # 페이지 생성
    "page_tool.create": (
        "필수: notion_db_id, plans[title,date,status,revisit,goal_intro,goals,summary]\n"
        "{\"payload\":{\"notion_db_id\":\"\",\"plans\":[{\"title\":\"학습 제목\",\"date\":\"2025-05-06T00:00:00Z\",\"status\":\"시작 전\",\"revisit\":false,\"goal_intro\":\"학습 목표 소개\",\"goals\":[\"목표1\",\"목표2\"],\"summary\":\"# 마크다운 형식 요약\\n내용...\"}]}}"
    ),

    # DB 페이지 조회
    "page_tool.list" : (
        "params.db_id 파라미터 넣을 시 특정 DB 페이지 리스트 조회\n"
        "파라미터 none: current DB의 리스트 조회"
    ),

    # DB 페이지 삭제
    "page_tool.delete" : (
        
    ),

    # DB 페이지 조회
    
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
        raise ValueError(f"{action} 액션에는 params.payload가 필요합니다.")

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

    path = spec["path"](params)
    url  = f"{STUDYAI_API}/{group.value}{path}"

    client = await get_client()
    log.debug("→ %s %s", spec["method"], url)

    try:
        res = await client.request(spec["method"], url, json=payload)
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

@mcp.tool(description="요청 예시(액션명.기능 -> 파라미터 형식 반환)")
def helper(action: str) -> str:
    examples = EXAMPLE_MAP
    return examples.get(action, "지원 안 함")




# ───────────────────────초기 가이드 prompt ───────────────────────
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

@mcp.prompt(name="Base Guide", description="기본 지시사항")
def base_guide() -> list[base.Message]:
    guide = (
        "툴 호출 시 한번에 한 요청만 처리합니다.\n"
        "사용자의 요청이 끝날 때까지 기다리고 처리합니다.\n"
        "모든 생성 요청 시 사용자의 요구사항을 반영해야 합니다\n"
        "반드시 사용자에게 확인 후 처리해야 합니다.\n"
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
