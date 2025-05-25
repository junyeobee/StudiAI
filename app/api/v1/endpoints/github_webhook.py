from fastapi import APIRouter, Depends, HTTPException, Body, Request, BackgroundTasks, status, Response
from app.services.github_webhook_service import GitHubWebhookService
from app.core.supabase_connect import get_supabase
from supabase._async.client import AsyncClient
from app.api.v1.dependencies.auth import require_user
from app.core.config import settings
from app.api.v1.dependencies.github import get_github_webhook_service
from app.utils.logger import api_logger
from app.utils.github_webhook_helper import GithubWebhookHelper
from app.api.v1.handler.github_webhook_handler import GitHubWebhookHandler

router = APIRouter()
public_router = APIRouter()

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_webhook(
    response: Response,
    repo_url: str = Body(..., description="GitHub 저장소 URL"),
    learning_db_id: str = Body(..., description="Notion 학습 DB ID"),
    events: list[str] = Body(default=["push"], description="구독할 이벤트 목록"),
    user_id: str = Depends(require_user),
    supabase: AsyncClient = Depends(get_supabase),
    github_service: GitHubWebhookService = Depends(get_github_webhook_service)
):
    """GitHub 웹훅 등록 + 메타 저장(db_webhooks)."""
    try:
        if not user_id:
            raise HTTPException(status_code=401, detail="인증이 필요합니다.")
        # 1) 저장소 파싱
        repo_owner, repo_name = await GithubWebhookHelper.parse_github_repo_url(repo_url)
        if not repo_owner or not repo_name:
            raise HTTPException(status_code=400, detail="유효하지 않은 GitHub 저장소 URL입니다.")

        # 2) secret 생성 & 웹훅 등록
        raw_secret = await GithubWebhookHelper.generate_secret()
        # 처리해야할 것 : 웹훅 존재할 시, 웹훅 있다고 알림
        callback_url = f"{settings.API_BASE_URL}/github_webhook_public/webhook_operation"
        webhook_data = await github_service.create_webhook(
            repo_owner=repo_owner,
            repo_name=repo_name,
            callback_url=callback_url,
            events=events,
            secret=raw_secret,
        )

        # 3) Supabase 저장
        encrypted_secret = await GithubWebhookHelper.encrypt_secret(raw_secret)
        webhook_record = {
            "learning_db_id": learning_db_id,
            "provider": "github",
            "webhook_id": str(webhook_data["id"]),
            "secret": encrypted_secret,
            "status": "active",
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "subscribed_events": events
        }
        res = await supabase.table("db_webhooks").upsert(webhook_record).execute()
        record_id = res.data[0]["id"] if res.data else webhook_record["id"]

        # 4) Location 헤더
        response.headers["Location"] = f"/github_webhook/{record_id}"

        return {
            "id": record_id,
            "webhook_id": webhook_data["id"],
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "events": events,
            "status": "active",
        }

    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(f"웹훅 생성 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/repos")
async def get_repo_list(
    github_service: GitHubWebhookService = Depends(get_github_webhook_service)
):
    """GitHub 저장소 목록 조회"""
    try:
        res = await github_service.list_repositories()
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@public_router.post("/webhook_operation")
async def handle_github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    supabase: AsyncClient = Depends(get_supabase)
):
    """GitHub 웹훅 이벤트 처리 엔드포인트"""
    handler = GitHubWebhookHandler(supabase)
    return await handler.handle_webhook(request, background_tasks)