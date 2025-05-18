"""
API 라우터 통합
"""
from fastapi import APIRouter
from app.api.v1.endpoints import databases, webhooks, learning, auth, notion_setting, github_webhook

api_router = APIRouter()
public_router = APIRouter()
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

# 인증 관련 엔드포인트
api_router.include_router(
    auth.router,
    prefix="/auth",
    tags=["auth"]
) 

api_router.include_router(
    notion_setting.router,
    prefix="/notion_setting",
    tags=["notion_setting"]
)

public_router.include_router(
    auth.public_router,
    prefix="/auth_public",
    tags=["auth_public"]
)

api_router.include_router(
    github_webhook.router,
    prefix="/github_webhook",
    tags=["github_webhook"]
)

