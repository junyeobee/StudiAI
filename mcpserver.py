import logging
import os
from contextlib import asynccontextmanager
from typing import Any, List

from starlette.middleware import Middleware
from fastmcp import FastMCP
from fastmcp.prompts.prompt import Message, TextContent

# 리팩토링된 모듈 임포트
from app.mcp.constants.app_settings import settings
from app.mcp.services.http_client import client_manager
from app.mcp.tools.mcp_tools import MCPTools
from app.mcp.middleware.auth_middleware import UnifiedAuthMiddleware

# ─────────────────────── 기본 설정 ───────────────────────
log = logging.getLogger("mcp")
logging.basicConfig(level=logging.INFO)


# ─────────────────────── FastMCP 라이프사이클 ───────────────────────
@asynccontextmanager
async def lifespan(server: FastMCP):
    """FastMCP 서버 시작/종료 시 실행되는 라이프사이클 이벤트"""
    log.info(f"'{server.name}' MCP 서버가 시작됩니다.")
    yield
    log.info("HTTP 클라이언트 세션을 닫습니다...")
    await client_manager.close()
    log.info(f"'{server.name}' MCP 서버가 종료됩니다.")


# ─────────────────────── FastMCP 서버 초기화 ───────────────────────
mcp = FastMCP(
    name="studyai",
    instructions=(
        "당신은 프로젝트/학습 관리 매니저입니다.\n"
        "노션 DB·웹훅을 관리합니다.\n"
    ),
    lifespan=lifespan,
)

# ─────────────────────── MCP 도구 등록 ───────────────────────
@mcp.tool(description=MCPTools.page_tool.__doc__)
async def page_tool(action: str, params: dict[str, Any]) -> str:
    return await MCPTools.page_tool(action, params)

@mcp.tool(description=MCPTools.database_tool.__doc__)
async def database_tool(action: str, params: dict[str, Any]) -> str:
    return await MCPTools.database_tool(action, params)

@mcp.tool(description=MCPTools.webhook_tool.__doc__)
async def webhook_tool(action: str, params: dict[str, Any]) -> str:
    return await MCPTools.webhook_tool(action, params)

@mcp.tool(description=MCPTools.notion_settings_tool.__doc__)
async def notion_settings_tool(action: str, params: dict[str, Any]) -> str:
    return await MCPTools.notion_settings_tool(action, params)

@mcp.tool(description=MCPTools.auth_tool.__doc__)
async def auth_tool(action: str, params: dict[str, Any]) -> str:
    return await MCPTools.auth_tool(action, params)

@mcp.tool(description=MCPTools.github_webhook_tool.__doc__)
async def github_webhook_tool(action: str, params: dict[str, Any]) -> str:
    return await MCPTools.github_webhook_tool(action, params)

@mcp.tool(description=MCPTools.helper.__doc__)
def helper(action: str) -> str:
    return MCPTools.helper(action)

@mcp.tool(description=MCPTools.user_guide.__doc__)
def user_guide(action: str = "default") -> str:
    return MCPTools.user_guide(action)


# ─────────────────────── 시스템 프롬프트 등록 ───────────────────────
@mcp.prompt(name="Essential Guidelines", description="필수 지침 사항")
def essential_guidelines() -> List[Message]:
    guide = (
        "⚠️ 필수 준수 사항 - 반드시 따라야 합니다! ⚠️\n\n"
        "1. 모든 변경성 액션(create/update/delete/activate/deactivate)은 반드시 사용자에게 실행 여부를 명확히 확인해야 합니다.\n"
        "   - 예: \"이 작업을 실행할까요? (yes/no)\"\n"
        "   - 사용자가 'yes' 또는 'confirm=True'와 같이 명시적으로 동의한 경우에만 `confirm=True` 파라미터를 포함하여 툴을 호출하세요.\n"
        "   - 사용자가 거부하면 작업을 즉시 중단하고 \"작업을 취소했습니다.\"라고 응답하세요.\n\n"
        "2. 시스템 운영 규칙:\n"
        "   - 한 번에 하나의 툴 호출만 처리하세요.\n"
        "   - 사용자의 요청이 완전히 끝날 때까지 기다린 후 다음 요청을 처리하세요.\n"
        "   - 어떤 경우에도 사용자 확인 없이는 데이터를 변경하는 작업을 실행하지 마세요.\n\n"
        "이 지침을 위반하면 심각한 데이터 오류가 발생할 수 있습니다."
    )
    return [Message(role="assistant", content=[TextContent(type="text", text=guide)])]

@mcp.prompt(name="Params Guide", description="툴 사용시 파라미터 형식 가이드")
def guidelines() -> List[Message]:
    guide = (
        "자세한 요청 예시는 `helper('툴이름.액션')`을 호출하여 확인하세요.\n"
        "호출 규칙 요약:\n"
        "**`params.payload`가 필요한 툴:**\n"
        "- `database_tool(create)`\n"
        "- `page_tool(create|update)`\n"
        "- `github_webhook_tool(create)`\n"
        "- `notion_settings_tool(set_active_workspace)`\n\n"
        "**날짜 형식:**\n"
        "- ISO 8601 형식 (예: `2025-05-06T00:00:00Z` 또는 `2025-05-06T09:00:00+09:00`)\n\n"
        "**`page_tool(update)` 참고:**\n"
        "- `summary` 필드는 기존 AI 요약 섹션에 내용을 *추가*합니다."
    )
    return [Message(role="user", content=[TextContent(type="text", text=guide)])]


# ─────────────────────── 서버 실행 ───────────────────────
if __name__ == "__main__":
    app_middleware = [Middleware(UnifiedAuthMiddleware)]

    mcp.run(
        transport="streamable-http",
        host=settings.DEFAULT_HOST,
        port=settings.DEFAULT_PORT,
        middleware=app_middleware,
    ) 