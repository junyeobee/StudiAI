from fastapi import APIRouter, Depends, HTTPException, Body
from app.services.github_webhook_service import GitHubWebhookService
from app.core.supabase_connect import get_supabase
from supabase._async.client import AsyncClient
from app.api.v1.dependencies.auth import require_user
from app.core.config import settings

router = APIRouter()


@router.post("/create")
async def create_webhook(
    repo_url: str = Body(..., description="GitHub 저장소 URL"),
    learning_db_id: str = Body(..., description="Notion 학습 DB ID"),
    personal_access_token: str = Body(..., description="GitHub 개인 액세스 토큰"),
    events: list[str] = Body(default=["push"], description="구독할 이벤트 목록"),
    user_id: str = Depends(require_user),
    supabase: AsyncClient = Depends(get_supabase)
):
    """GitHub 웹훅 직접 생성"""
    try:
        # 1. 저장소 정보 파싱
        repo_owner, repo_name = await GitHubWebhookService.parse_github_repo_url(repo_url)
        
        if not repo_owner or not repo_name:
            raise HTTPException(status_code=400, detail="유효하지 않은 GitHub 저장소 URL입니다.")
        
        # 2. 콜백 URL 구성
        callback_url = f"{settings.API_BASE_URL}/api/v1/webhooks/github"
        
        # 3. 웹훅 생성
        webhook_data = await GitHubWebhookService.create_webhook_with_pat(
            repo_owner=repo_owner,
            repo_name=repo_name,
            callback_url=callback_url,
            personal_access_token=personal_access_token,
            events=events
        )
        
        # 4. DB에 웹훅 정보 저장
        webhook_record = {
            "learning_db_id": learning_db_id,
            "provider": "github",
            "webhook_id": str(webhook_data["id"]),
            "repo_owner": repo_owner,
            "repo_name": repo_name,
            "secret": webhook_data["secret"],
            "status": "active",
            "subscribed_events": events,
            "created_by": user_id
        }
        
        res = await supabase.table("db_webhooks").insert(webhook_record).execute()
        
        if not res.data:
            raise HTTPException(status_code=500, detail="웹훅 정보 저장 실패")
        
        return {
            "status": "success",
            "message": "GitHub 웹훅이 성공적으로 생성되었습니다.",
            "data": {
                "webhook_id": webhook_data["id"],
                "repo_owner": repo_owner,
                "repo_name": repo_name,
                "events": events
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))