from fastapi import APIRouter, Depends, HTTPException, Body, Request, BackgroundTasks,status,Response
from app.services.github_webhook_service import GitHubWebhookService
from app.core.supabase_connect import get_supabase
from supabase._async.client import AsyncClient
from app.api.v1.dependencies.auth import require_user
from app.core.config import settings
from app.api.v1.dependencies.github import get_github_webhook_service
from typing import Any
from app.utils.logger import api_logger
from app.utils.github_webhook_helper import GithubWebhookHelper
import json
import hmac
import hashlib
from app.services.auth_service import get_integration_token
import re

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
        if not user_id :
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
    """GitHub 가 푸시하는 웹훅 이벤트. 시그니처 검증 뒤 push 이벤트만 백그라운드로 전달."""
    try:
        body_bytes = await request.body()
        headers = request.headers
        signature = headers.get("X-Hub-Signature-256")
        if not signature:
            raise HTTPException(401, "Signature missing")

        # 1) Payload JSON 파싱 → 저장소 정보 추출
        payload: dict[str, Any] = json.loads(body_bytes)
        repo_full = payload.get("repository", {}).get("full_name")
        if not repo_full or "/" not in repo_full:
            return {"status": "success"}
        owner, repo = repo_full.split("/", 1)

        # 2) 해당 repo 의 활성 웹훅 rows 조회
        res = await supabase.table("db_webhooks") \
                .select("secret, learning_db_id, created_by") \
                .eq("repo_owner", owner) \
                .eq("repo_name", repo) \
                .eq("status", "active") \
                .execute()

        print("테스트 difftestasdfasdfasdfa")

        rows = res.data
        if not rows:
            return {"status": "success"}

        # 3) 서명 검증
        verified_row = None
        for row in rows:
            raw_secret = await GithubWebhookHelper.decrypt_secret(row["secret"])
            expected = "sha256=" + hmac.new(raw_secret.encode(), body_bytes, hashlib.sha256).hexdigest()
            if hmac.compare_digest(expected, signature):
                verified_row = row
                break
        if not verified_row:
            raise HTTPException(401, "Invalid signature")

        event_type = headers.get("X-GitHub-Event")
        
        match event_type :
            case "push":
                code_bundle = await GithubWebhookHelper.process_github_push_event(payload)
                
                decrypted_pat = await get_integration_token(verified_row["created_by"], "github", supabase)
                github_service = GitHubWebhookService(token=decrypted_pat)
                for b in code_bundle:
                    commit_detail = await github_service.fetch_commit_detail(owner, repo, b["sha"])
                    for file in commit_detail["files"]:
                        if file["status"] == "modified":
                            print(file["filename"])
                            print(re.sub(r"^[0-9]*\+\s+", "", file["patch"], flags=re.MULTILINE))
                        if file["status"] == "added":
                            print(file["filename"])
                            print(re.sub(r"^[0-9]*\+\s+", "", file["patch"], flags=re.MULTILINE))

                        
            case _:
                pass
            

        return {"status": "success"}

    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(f"웹훅 처리 실패: {e}")
        # GitHub 재시도 방지를 위해 200 계열 응답 유지
        return {"status": "success"}
