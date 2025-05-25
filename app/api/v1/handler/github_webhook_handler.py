from fastapi import HTTPException, Request, BackgroundTasks
from app.utils.github_webhook_helper import GithubWebhookHelper
from app.services.github_webhook_service import GitHubWebhookService
from app.services.auth_service import get_integration_token
from app.services.supa import get_active_webhooks
from supabase._async.client import AsyncClient
from typing import Dict, List, Optional, Tuple
from app.utils.logger import api_logger
from worker.tasks import task_queue, analyze_code_task
import json
import hmac
import hashlib

class GitHubWebhookHandler:
    """GitHub 웹훅 처리를 담당하는 핸들러 클래스"""
    def __init__(self, supabase: AsyncClient):
        self.supabase = supabase
    
    async def handle_webhook(self, request: Request, background_tasks: BackgroundTasks) -> Dict:
        """메인 핸들러 함수: 웹훅 처리의 전체 흐름 관리"""
        try:
            api_logger.info("===== 웹훅 요청 수신 =====")
            # 1. 요청 데이터 추출 및 검증
            body_bytes, headers = await self._extract_request_data(request)
            signature = headers.get("X-Hub-Signature-256")
            event_type = headers.get("X-GitHub-Event")
            api_logger.info(f"웹훅 이벤트 유형: {event_type}")
            
            if not signature:
                raise HTTPException(401, "Signature missing")
                
            # 2. 페이로드 파싱 및 저장소 정보 추출
            payload = self._parse_payload(body_bytes)
            owner, repo = self._extract_repo_info(payload)
            api_logger.info(f"저장소 정보: {owner}/{repo}")
            
            if not owner or not repo:
                return {"status": "success"}
                
            # 3. 웹훅 정보 조회 및 서명 검증
            webhook_rows = await self._get_active_webhooks(owner, repo)
            api_logger.info(f"활성 웹훅 수: {len(webhook_rows)}")
            
            if not webhook_rows:
                return {"status": "success"}
                
            verified_row = await self._verify_signature(webhook_rows, body_bytes, signature)
            if not verified_row:
                raise HTTPException(401, "Invalid signature")
            
            api_logger.info(f"서명 검증 성공, 사용자 ID: {verified_row['created_by']}")
            
            # 4. 이벤트 유형에 따른 처리
            if event_type == "push":
                api_logger.info("푸시 이벤트 처리 시작")
                await self._process_push_event(payload, verified_row, owner, repo)
            
            return {"status": "success"}
            
        except HTTPException:
            raise
        except Exception as e:
            api_logger.error(f"웹훅 처리 실패: {e}")
            # GitHub 재시도 방지를 위해 200 계열 응답 유지
            return {"status": "success"}
    
    async def _extract_request_data(self, request: Request) -> Tuple[bytes, Dict]:
        """요청에서 본문과 헤더 추출"""
        body_bytes = await request.body()
        headers = request.headers
        return body_bytes, headers
    
    def _parse_payload(self, body_bytes: bytes) -> Dict:
        """JSON 페이로드 파싱"""
        return json.loads(body_bytes)
    
    def _extract_repo_info(self, payload: Dict) -> Tuple[Optional[str], Optional[str]]:
        """저장소 정보 추출"""
        repo_full = payload.get("repository", {}).get("full_name")
        if not repo_full or "/" not in repo_full:
            return None, None
            
        owner, repo = repo_full.split("/", 1)
        return owner, repo
    
    async def _get_active_webhooks(self, owner: str, repo: str) -> List[Dict]:
        """활성 웹훅 정보 조회"""
        res = await get_active_webhooks(owner, repo, self.supabase)
        return res.data
    
    async def _verify_signature(self, webhook_rows: List[Dict], body_bytes: bytes, signature: str) -> Optional[Dict]:
        """서명 검증"""
        for row in webhook_rows:
            raw_secret = await GithubWebhookHelper.decrypt_secret(row["secret"])
            expected = "sha256=" + hmac.new(raw_secret.encode(), body_bytes, hashlib.sha256).hexdigest()
            if hmac.compare_digest(expected, signature):
                return row
                
        return None
    
    async def _process_push_event(self, payload: Dict, verified_row: Dict, owner: str, repo: str):
        """푸시 이벤트 처리 - RQ 태스크로 분석 작업 위임"""
        # 1. 커밋 정보 추출
        api_logger.info("커밋 정보 추출 시작")
        code_bundle = await GithubWebhookHelper.process_github_push_event(payload)
        api_logger.info(f"추출된 커밋 수: {len(code_bundle)}")
        
        # 2. GitHub 토큰 가져오기
        api_logger.info("GitHub 토큰 가져오기")
        decrypted_pat = await get_integration_token(verified_row["created_by"], "github", self.supabase)
        github_service = GitHubWebhookService(token=decrypted_pat)
        
        # 3. 각 커밋에 대해 RQ 태스크 등록
        for i, commit in enumerate(code_bundle):
            api_logger.info(f"커밋 {i+1}/{len(code_bundle)} 분석 태스크 등록: {commit['sha'][:8]}")
            
            # 커밋 상세 정보 조회
            commit_detail = await github_service.fetch_commit_detail(owner, repo, commit["sha"])
            files = commit_detail.get("files", [])
            
            # 수정된 파일들에 대해 전체 내용 가져오기
            for file in files:
                status = file.get("status", "")
                filename = file.get("filename", "")
                
                if status == "modified" and "patch" in file:
                    try:
                        file_content = await github_service.fetch_file_content(
                            owner=owner,
                            repo=repo,
                            path=filename,
                            ref=commit["sha"]
                        )
                        file["full_content"] = file_content
                        api_logger.info(f"파일 '{filename}' 전체 내용 가져옴")
                    except Exception as e:
                        api_logger.error(f"파일 '{filename}' 전체 내용 가져오기 실패: {str(e)}")
                
                elif status == "added":
                    if "patch" in file:
                        file["full_content"] = file["patch"]
                        api_logger.info(f"새 파일 '{filename}' patch에서 내용 가져옴")
                    else:
                        # 새 파일인데 patch가 없는 비정상적인 경우 - GitHub API로 fallback
                        api_logger.warning(f"새 파일 '{filename}'에 patch가 없음! GitHub API로 fallback 시도")
                        try:
                            file_content = await github_service.fetch_file_content(
                                owner=owner,
                                repo=repo,
                                path=filename,
                                ref=commit["sha"]
                            )
                            file["full_content"] = file_content
                            api_logger.info(f"새 파일 '{filename}' 내용 GitHub API로 가져옴")
                        except Exception as e:
                            api_logger.error(f"새 파일 '{filename}' 내용 가져오기 실패: {str(e)}")
            
            # RQ 태스크로 분석 작업 등록
            job = task_queue.enqueue(
                analyze_code_task,
                files=files,
                owner=owner,
                repo=repo,
                commit_sha=commit["sha"],
                user_id=verified_row["created_by"]
            )
            
            api_logger.info(f"커밋 {commit['sha'][:8]} 분석 태스크 등록 완료 - Job ID: {job.id}")
        
        api_logger.info(f"총 {len(code_bundle)}개 커밋 분석 태스크 등록 완료")