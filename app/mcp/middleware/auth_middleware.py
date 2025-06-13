from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from supabase import create_client
import os
import logging

from app.mcp.services.auth_service import SupabaseTokenAuth

log = logging.getLogger("mcp")

class UnifiedAuthMiddleware(BaseHTTPMiddleware):
    """
    쿼리 파라미터 토큰 추출과 Supabase 토큰 검증을 모두 처리하는 통합 인증 미들웨어.
    인증에 실패하면 즉시 401 응답을 반환하고, 성공 시에만 다음으로 넘어갑니다.
    """
    def __init__(self, app):
        super().__init__(app)
        self.auth_provider = self._initialize_auth_provider()

    def _initialize_auth_provider(self) -> SupabaseTokenAuth | None:
        """Supabase 클라이언트 및 인증 프로바이더를 초기화합니다."""
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        if supabase_url and supabase_key:
            try:
                supabase_client = create_client(supabase_url, supabase_key)
                log.info("인증 미들웨어 내 Supabase 클라이언트 초기화 성공.")
                return SupabaseTokenAuth(supabase_client)
            except Exception as e:
                log.error(f"인증 미들웨어 내 Supabase 클라이언트 초기화 실패: {e}")
        log.warning("인증 미들웨어: Supabase URL/KEY 미설정으로 인증 비활성화.")
        return None

    async def dispatch(self, request: Request, call_next) -> Response:
        # FastMCP의 기본 인증이 이미 유효한 Authorization 헤더를 처리했다면 통과
        if "authorization" in request.headers:
             # 여기서 FastMCP의 내장 로직이 처리하도록 그냥 넘김
             # 실제로는 FastMCP에 auth=None을 주었으므로 이 로직은 거의 실행되지 않음
             return await call_next(request)

        token = request.query_params.get("token") or request.query_params.get("access_token")

        if not token:
            log.warning("인증 실패: 요청에 토큰이 없습니다.")
            return Response("Unauthorized", status_code=401)

        if not self.auth_provider:
            log.error("인증 실패: 인증 서비스가 초기화되지 않았습니다.")
            return Response("Internal Server Error: Auth service not configured", status_code=500)

        access_token_obj = await self.auth_provider.load_access_token(token)
        
        if access_token_obj:
            # 인증 성공 시, FastMCP가 인식할 수 있도록 scope에 사용자 정보 추가
            request.scope["user"] = {
                "id": access_token_obj.client_id,
                "client_id": access_token_obj.client_id,
                "scopes": access_token_obj.scopes,
            }

            # 다음 검문소(FastMCP)가 요구하는 Authorization 헤더를 직접 만들어 붙여줍니다.
            # b''는 바이트 문자열을 의미합니다.
            auth_header = f"Bearer {token}".encode('utf-8')
            
            # 기존 헤더를 순회하며 authorization 헤더가 있는지 확인하고, 있다면 교체하고, 없다면 추가합니다.
            headers = request.scope['headers']
            auth_header_found = False
            for i, (key, value) in enumerate(headers):
                if key == b'authorization':
                    headers[i] = (b'authorization', auth_header)
                    auth_header_found = True
                    break
            
            if not auth_header_found:
                headers.append((b'authorization', auth_header))

            return await call_next(request)
        else:
            # 인증 실패 시, 여기서 요청을 중단하고 401 반환
            log.warning(f"인증 실패: 유효하지 않은 토큰입니다. Token: {token[:10]}...")
            return Response("Unauthorized", status_code=401) 