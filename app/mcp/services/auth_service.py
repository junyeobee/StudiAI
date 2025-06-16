import hashlib
import logging
from typing import Optional

# Auth types
from mcp.server.auth.provider import AccessToken  # type: ignore
from fastmcp.server.auth.auth import OAuthProvider
from supabase._async.client import AsyncClient

from app.mcp.constants.app_settings import settings
from app.services.supa_auth_service import get_user_by_key_hash

log = logging.getLogger("mcp")

class SupabaseTokenAuth(OAuthProvider):
    """Supabase `mcp_users` 테이블의 SHA-256 해시 토큰을 검증하는 OAuthProvider."""

    def __init__(self, supabase: AsyncClient):
        # OAuthProvider 기본 필드 설정 (필수)
        super().__init__(
            issuer_url="https://local.supabase.auth",  # 의미없는 placeholder
            required_scopes=None,
        )
        self.supabase = supabase

    async def load_access_token(self, token: str) -> Optional[AccessToken]:
        """Bearer 토큰을 검증하고 AccessToken 반환."""
        if len(token) < settings.MIN_TOKEN_LENGTH:
            return None

        hashed_token = hashlib.sha256(token.encode()).hexdigest()
        
        # 원본 로직과 동일하게 try-except 없이 직접 호출
        res = await get_user_by_key_hash(hashed_token, self.supabase)
        
        if not res or not res.data:
            return None

        user_row = res.data[0]
        user_id = str(user_row.get("user_id", "unknown"))

        return AccessToken(
            token=token,
            client_id=user_id,
            scopes=[],
            expires_at=None,
        )

    # ─────────────────────── UNUSED OAuth METHODS ───────────────────────

    async def get_client(self, client_id):
        return None

    async def register_client(self, client_info):
        raise NotImplementedError

    async def authorize(self, client, params):
        raise NotImplementedError

    async def load_authorization_code(self, client, authorization_code):
        return None

    async def exchange_authorization_code(self, client, authorization_code):
        raise NotImplementedError

    async def load_refresh_token(self, client, refresh_token):
        return None

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        raise NotImplementedError

    async def revoke_token(self, token):
        raise NotImplementedError 