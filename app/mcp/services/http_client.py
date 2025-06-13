import httpx
from typing import Optional
from app.mcp.constants.app_settings import settings

class HTTPClientManager:
    """HTTP 클라이언트 싱글톤 매니저"""
    
    def __init__(self, timeout: float = settings.HTTP_TIMEOUT):
        self._client: Optional[httpx.AsyncClient] = None
        self._timeout = timeout

    async def get(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        if self._client and self._client.is_closed is False:
            await self._client.aclose()

client_manager = HTTPClientManager() 