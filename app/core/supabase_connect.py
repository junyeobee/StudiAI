from supabase._async.client import AsyncClient, create_client
from fastapi import Request
from app.core.config import settings

async def init_supabase() -> AsyncClient:
    """Supabase 클라이언트 초기화 (FastAPI 시작 시 한 번만 호출)"""
    return await create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

async def get_supabase(request: Request) -> AsyncClient:
    """의존성 주입을 위한 Supabase 클라이언트 제공자"""
    return request.app.state.supabase
