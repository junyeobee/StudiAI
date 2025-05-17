from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.supabase_connect import init_supabase
from app.utils.logger import api_logger
from app.core.redis_connect import init_redis_client
from app.core.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 수명 주기 관리"""
    # 시작 시 실행
    try:
        # Supabase 클라이언트 초기화 및 app.state에 저장
        app.state.supabase = await init_supabase()
        api_logger.info("Supabase 클라이언트 초기화 완료")
        app.state.redis = await init_redis_client()
        api_logger.info("Redis 클라이언트 초기화 완료")
        yield
    except Exception as e:
        api_logger.error(f"Supabase 클라이언트 초기화 실패: {str(e)}")
        raise
    finally:
        # 종료 시 실행
        try:
            if hasattr(app.state, "supabase"):
                await app.state.supabase.auth.sign_out()
                api_logger.info("Supabase 클라이언트 정리 완료")

            if hasattr(app.state, "redis"):
                app.state.redis.close()
                api_logger.info("Redis 클라이언트 정리 완료")
        except Exception as e:
            api_logger.error(f"Supabase 클라이언트 정리 실패: {str(e)}")
            api_logger.error(f"Redis 클라이언트 정리 실패: {str(e)}")