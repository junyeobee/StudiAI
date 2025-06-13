from typing import Any
from app.mcp.models.api import Group
from app.mcp.services.api_service import APIService
from app.mcp.constants.examples import EXAMPLE_MAP
from app.mcp.constants.user_guide import USER_GUIDE

class MCPTools:
    """MCP 도구들을 정적 메서드로 모아놓은 클래스"""
    
    @staticmethod
    async def page_tool(action: str, params: dict[str, Any]) -> str:
        """Notion 페이지 관련 액션 처리 (list|create|update|delete|get|commits|commit_sha)"""
        return await APIService.dispatch(Group.PAGE, action, params)

    @staticmethod
    async def database_tool(action: str, params: dict[str, Any]) -> str:
        """학습 DB 관련 액션 처리 (list|current|create|activate|deactivate|update)"""
        return await APIService.dispatch(Group.DB, action, params)

    @staticmethod
    async def webhook_tool(action: str, params: dict[str, Any]) -> str:
        """웹훅 작업 이력 관리 (failed|list|detail)"""
        return await APIService.dispatch(Group.WEB, action, params)

    @staticmethod
    async def notion_settings_tool(action: str, params: dict[str, Any]) -> str:
        """노션 설정 관련 액션 처리 (workspaces|set_active_workspace|top_pages|set_top_page|get_top_page)"""
        return await APIService.dispatch(Group.NOTION_SETTINGS, action, params)

    @staticmethod
    async def auth_tool(action: str, params: dict[str, Any]) -> str:
        """토큰 발급 액션 처리 (get_token)"""
        return await APIService.dispatch(Group.AUTH, action, params)

    @staticmethod
    async def github_webhook_tool(action: str, params: dict[str, Any]) -> str:
        """GitHub 웹훅 관련 액션 처리 (create|repos)"""
        return await APIService.dispatch(Group.GITHUB_WEBHOOK, action, params)

    @staticmethod
    def helper(action: str) -> str:
        """요청 형식 예시 반환. action 형식: 'tool_name.action' (예: 'database_tool.create')"""
        return EXAMPLE_MAP.get(action, f"'{action}'에 대한 예시를 찾을 수 없습니다.")

    @staticmethod
    def user_guide(action: str = "default") -> str:
        """기능별 사용자 가이드 반환. action: [default|Database|Page|Notion_Settings|Auth|Webhook|GitHub_Webhook]"""
        return USER_GUIDE.get(action, f"'{action}'에 대한 가이드를 찾을 수 없습니다.") 