"""
메인 애플리케이션
"""
from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.utils.logger import setup_logging
from app.api.v1.api import api_router, public_router
from app.core.events import lifespan
from app.api.v1.dependencies.auth import require_user
from fastapi.security import HTTPBearer
from app.utils.logger import api_logger
from app.core.exception_handlers import register_exception_handlers
from app.middleware.auth_middleware import AuthMiddleware

# 로깅 설정
setup_logging()

bearer_scheme = HTTPBearer()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.APP_VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
    debug=False
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 인증 미들웨어 등록 (lifespan 이벤트에서 supabase 클라이언트 설정됨)
@app.middleware("http")
async def auth_middleware_wrapper(request, call_next):
    """인증 미들웨어 래퍼 - app.state.supabase 사용"""
    # AuthMiddleware 인스턴스 생성 시 supabase 클라이언트 전달
    middleware = AuthMiddleware(
        app=app, 
        supabase_client=getattr(app.state, 'supabase', None)
    )
    return await middleware.dispatch(request, call_next)

# 전역 예외 핸들러 등록
register_exception_handlers(app)

# API 라우터 등록
app.include_router(api_router, dependencies=[Depends(require_user)])
app.include_router(public_router)

@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {"message": "Notion 학습 관리 시스템 API"}

#───────────────나중에 삭제할 부분(Swagger 인증 설정)
original_openapi = app.openapi

# Swagger 인증 설정
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = original_openapi()
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer"
        }
    }
    openapi_schema["security"] = [{"BearerAuth": []}]
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)