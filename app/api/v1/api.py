"""
API 라우터 통합
"""
from fastapi import APIRouter
from app.api.v1.endpoints import databases, webhooks, learning

api_router = APIRouter()

# 데이터베이스 관련 엔드포인트
api_router.include_router(
    databases.router,
    prefix="/databases",
    tags=["databases"]
)

# 웹훅 관련 엔드포인트
api_router.include_router(
    webhooks.router,
    prefix="/webhooks",
    tags=["webhooks"]
)

# 학습 관련 엔드포인트
api_router.include_router(
    learning.router,
    prefix="/learning",
    tags=["learning"]
) 