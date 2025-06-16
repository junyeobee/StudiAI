"""
API 라우터 통합
"""
from fastapi import APIRouter
from app.api.v1.endpoints import (
    databases, webhooks, learning, auth, notion_setting, github_webhook, worker, notion_webhook, health, admin, feedback
    )

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

# 관리자 관련 엔드포인트 (에러 통계 등)
api_router.include_router(
    admin.router,
    prefix="/admin",
    tags=["admin"]
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

public_router.include_router(
    github_webhook.public_router,
    prefix="/github_webhook_public",
    tags=["github_webhook_public"]
)

api_router.include_router(
    worker.router,
    prefix="/worker",
    tags=["worker"]
)

# ✅ 헬스체크 엔드포인트 등록 (인증 불필요)
public_router.include_router(
    health.router,
    prefix="/health",
    tags=["health"]
)

public_router.include_router(
    notion_webhook.router,
    prefix="/notion_webhook_public",
    tags=["notion_webhook_public"]
)

api_router.include_router(
    feedback.router,
    prefix="/feedback",
    tags=["feedback"]
)