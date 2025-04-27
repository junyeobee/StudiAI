"""
메인 애플리케이션
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.utils.logger import setup_logging
from app.api.v1.api import api_router
from app.api.v1.endpoints import databases, webhooks, learning
from app.core.events import register_startup, register_shutdown

# 로깅 설정
setup_logging()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 이벤트 핸들러 등록
register_startup(app)
register_shutdown(app)

# API 라우터 등록
app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(databases.router, prefix="/databases", tags=["databases"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
app.include_router(learning.router, prefix="/learning", tags=["learning"])

@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {"message": "Notion 학습 관리 시스템 API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)