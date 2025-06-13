import logging
from typing import Optional, Any
import httpx
from pydantic import ValidationError
from fastmcp.server.dependencies import get_http_headers
from app.mcp.constants.app_settings import settings
from app.mcp.models.api import Group
from app.mcp.routes.action_map import ACTION_MAP, PAYLOAD_MODEL
from app.mcp.services.http_client import client_manager
from app.mcp.constants.examples import EXAMPLE_MAP

log = logging.getLogger("mcp")

class APIService:
    """API 요청 처리 서비스"""
    
    @staticmethod
    def _resolve_api_key() -> Optional[str]:
        """HTTP 헤더에서 Bearer 토큰을 우선적으로 가져오고, 없으면 None을 반환."""
        try:
            headers = get_http_headers()
            auth_header: str | None = headers.get("authorization")
            if auth_header:
                if auth_header.lower().startswith("bearer "):
                    token = auth_header[7:].strip()
                else:
                    token = auth_header.strip()

                if len(token) >= settings.MIN_TOKEN_LENGTH:
                    return token
        except Exception:
            # get_http_headers()는 요청 컨텍스트 외부에서 호출되면 예외 발생
            pass
        return None

    @staticmethod
    def _validate_payload(group: Group, action: str, params: dict) -> Optional[dict]:
        """Payload 유효성 검증 및 Pydantic 모델 변환"""
        spec = ACTION_MAP[group][action]
        if not spec["needs_json"]:
            return None

        raw_payload = params.get("payload")
        if raw_payload is None:
            tool_name = f"{group.value.replace('_','-')}_tool.{action}"
            error_msg = (
                f"❌ {tool_name} 액션은 `params.payload`가 필수입니다.\n\n"
                f"📖 올바른 형식은 `helper('{tool_name}')`를 호출하여 확인하세요.\n"
                f"💡 예시:\n{EXAMPLE_MAP.get(tool_name, '해당 액션에 대한 예시가 없습니다.')}"
            )
            raise ValueError(error_msg)

        model_cls = PAYLOAD_MODEL.get((group, action))
        if model_cls is None:
            return raw_payload

        try:
            validated_model = model_cls.model_validate(raw_payload)
            return validated_model.model_dump(mode="json")
        except ValidationError as ve:
            tool_name = f"{group.value.replace('_','-')}_tool.{action}"
            error_details = [
                f"  • 필드 `{' -> '.join(map(str, error['loc']))}`: {error['msg']}"
                for error in ve.errors()
            ]
            error_msg = (
                f"❌ `payload` 검증에 실패했습니다.\n\n"
                f"🔍 오류 내용:\n" + '\n'.join(error_details) + "\n\n"
                f"📖 올바른 형식은 `helper('{tool_name}')`를 호출하여 확인하세요.\n"
                f"💡 예시:\n{EXAMPLE_MAP.get(tool_name, '해당 액션에 대한 예시가 없습니다.')}"
            )
            raise ValueError(error_msg) from ve

    @staticmethod
    async def dispatch(group: Group, action: str, params: dict) -> Any:
        """API 요청을 Studiai 서버로 디스패치"""
        spec = ACTION_MAP[group].get(action)
        if not spec:
            return f"`{group.value}` 그룹에서 지원하지 않는 action_tool '{action}'입니다."
        
        try:
            payload = APIService._validate_payload(group, action, params)
        except ValueError as e:
            return str(e)
        
        api_token = APIService._resolve_api_key()
        if not api_token:
            return "인증 오류: 유효한 Bearer 토큰을 포함한 Authorization 헤더가 필요합니다."
        
        headers = {"Authorization": f"Bearer {api_token}"}

        if spec["method"] in ('POST', 'PATCH', 'DELETE', 'PUT'):
            if not params.get("confirm"):
                return "사용자의 확인이 필요한 작업입니다. 계속하려면 요청에 `params.confirm=True`를 포함하여 다시 시도해주세요. 취소하려면 이 요청을 무시하세요."

        path = spec["path"](params)
        url = f"{settings.STUDYAI_API}/{group.value}{path}"
        
        client = await client_manager.get()
        log.debug("→ %s %s", spec["method"], url)

        try:
            res = await client.request(spec["method"], url, json=payload, headers=headers)
            res.raise_for_status()
            
            if res.status_code == 204: # No Content
                return "성공적으로 처리되었습니다."

            if res.headers.get("content-type", "").startswith("application/json"):
                return res.json()
            
            return res.text or "성공적으로 처리되었습니다."

        except httpx.HTTPStatusError as e:
            try:
                error_response = e.response.json()
                detail = error_response.get("detail", f"HTTP {e.response.status_code} 오류")
                return f"오류: {detail}"
            except Exception:
                return f"HTTP {e.response.status_code} 오류가 발생했습니다: {e.response.text}"
        except httpx.RequestError as e:
            log.error(f"Studiai API 요청 오류: {e}")
            return "네트워크 연결 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
        except Exception as e:
            log.error(f"API 디스패치 중 예상치 못한 오류 발생: {e}", exc_info=True)
            return "알 수 없는 오류가 발생했습니다." 