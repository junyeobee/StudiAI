from fastapi import FastAPI
from supabase._async.client import AsyncClient
from app.services.supa import init_supabase
from app.utils.logger import api_logger

def register_startup(app: FastAPI):
    @app.on_event("startup")
    async def _():
        """애플리케이션 시작 시 Supabase 클라이언트 초기화"""
        try:
            app.state.supabase = await init_supabase()
            api_logger.info("Supabase 클라이언트 초기화 완료")
        except Exception as e:
            api_logger.error(f"Supabase 클라이언트 초기화 실패: {str(e)}")
            raise

def register_shutdown(app: FastAPI):
    @app.on_event("shutdown")
    async def _():
        """애플리케이션 종료 시 Supabase 클라이언트 정리"""
        try:
            if hasattr(app.state, "supabase"):
                await app.state.supabase.auth.sign_out()
                api_logger.info("Supabase 클라이언트 정리 완료")
        except Exception as e:
            api_logger.error(f"Supabase 클라이언트 정리 실패: {str(e)}") 