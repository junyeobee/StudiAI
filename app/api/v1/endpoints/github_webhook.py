from fastapi import APIRouter, Depends, HTTPException, Body, Request, BackgroundTasks, status, Response
from app.services.github_webhook_service import GitHubWebhookService
from app.core.supabase_connect import get_supabase
from supabase._async.client import AsyncClient
from app.api.v1.dependencies.auth import require_user
from app.core.config import settings
from app.api.v1.dependencies.github import get_github_webhook_service
from typing import Any, Dict, List, Optional, Tuple
from app.utils.logger import api_logger
from app.utils.github_webhook_helper import GithubWebhookHelper
import json
import hmac
import hashlib
from app.services.auth_service import get_integration_token
from redis.asyncio import Redis
from app.core.redis_connect import get_redis
import asyncio
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


class CodeAnalysisService:
    """코드 분석 및 LLM 처리를 담당하는 서비스"""
    
    def __init__(self, redis_client: Redis, supabase: AsyncClient):
        self.redis_client = redis_client
        self.supabase = supabase
        self.queue = asyncio.Queue()  # 비동기 큐
    
    async def analyze_code_changes(self, files: List[Dict], owner: str, repo: str, commit_sha: str, user_id: str):
        """코드 변경 분석 진입점"""
        api_logger.info(f"분석할 파일 수: {len(files)}")
        tasks = []
        for file in files:
            if "patch" not in file:
                continue
                
            clean_code = self._strip_patch(file["patch"])
            api_logger.info(f"파일 '{file['filename']}' 분석 큐에 추가")
            tasks.append(self._enqueue_code_analysis(
                clean_code, 
                file["filename"], 
                commit_sha, 
                user_id
            ))
        
        await asyncio.gather(*tasks)
        api_logger.info("모든 코드 분석 작업이 큐에 추가됨")
    
    def _strip_patch(self, patch: str) -> str:
        """패치에서 라인 번호와 '+' 기호 제거"""
        return re.sub(r"(?m)^(\d*\+|\+)\s+", "", patch)
    
    async def _enqueue_code_analysis(self, code: str, filename: str, commit_sha: str, user_id: str):
        """코드 분석 작업을 큐에 넣음"""
        # 코드가 길면 적절히 분할
        chunks = self._split_code_if_needed(code)
        
        for i, chunk in enumerate(chunks):
            metadata = self._extract_metadata(chunk)
            await self.queue.put({
                "code": chunk,
                "metadata": metadata,
                "filename": filename,
                "commit_sha": commit_sha,
                "user_id": user_id,
                "chunk_index": i,
                "total_chunks": len(chunks)
            })
            api_logger.info(f"'{filename}' 청크 {i+1}/{len(chunks)} 큐에 추가됨")
    
    def _split_code_if_needed(self, code: str) -> List[str]:
        """코드가 너무 길면 여러 청크로 분할"""
        # 임시로 단순 구현 - 실제로는 토큰 수나 함수/클래스 단위로 분할 필요
        max_length = 3000  # 예시 길이 제한
        
        if len(code) <= max_length:
            return [code]
            
        # 단순하게 청크 단위로 분할 (실제로는 더 정교한 로직 필요)
        chunks = []
        for i in range(0, len(code), max_length):
            chunks.append(code[i:i+max_length])
        
        return chunks
    
    def _extract_metadata(self, code: str) -> Dict[str, Any]:
        """코드 청크에서 메타데이터 추출"""
        metadata = {}
        
        # 주석에서 메타데이터 추출 로직
        lines = code.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('#'):
                # [파일경로] 형식 추출
                if '[' in line and ']' in line:
                    match = re.search(r'\[(.*?)\]', line)
                    if match:
                        metadata['reference_file'] = match.group(1)
                
                # {응답 형식} 형식 추출
                if '{' in line and '}' in line:
                    match = re.search(r'\{(.*?)\}', line)
                    if match:
                        metadata['response_format'] = match.group(1)
                
                # (요구사항) 형식 추출
                if '(' in line and ')' in line:
                    match = re.search(r'\((.*?)\)', line)
                    if match:
                        metadata['requirements'] = match.group(1)
                
                # 일반 주석 텍스트
                metadata['comment'] = line.lstrip('#').strip()
                # 첫 번째 주석만 처리하고 중단
                break
        
        return metadata
    
    async def process_queue(self):
        """비동기로 큐 처리"""
        api_logger.info("코드 분석 큐 처리 시작")
        while True:
            item = await self.queue.get()
            try:
                api_logger.info(f"코드 분석 처리: {item['filename']} 청크 {item['chunk_index']+1}/{item['total_chunks']}")
                # LLM API 호출 및 결과 저장
                result = await self._call_llm_api(item)
                await self._store_analysis_result(item, result)
            except Exception as e:
                api_logger.error(f"코드 분석 처리 실패: {str(e)}")
            finally:
                self.queue.task_done()
    
    async def _call_llm_api(self, item: Dict) -> str:
        """LLM API 호출 (실제 구현 필요)"""
        # 임시 구현 - 실제 LLM API 호출로 대체 필요
        api_logger.info(f"LLM API 호출: {item['filename']} 청크 {item['chunk_index']+1}")
        # TODO: 실제 LLM API 호출 구현
        return f"코드 분석 결과: {item['filename']}"
    
    async def _store_analysis_result(self, item: Dict, result: str):
        """분석 결과 저장"""
        api_logger.info(f"분석 결과 저장: {item['filename']} 청크 {item['chunk_index']+1}")
        
        key = f"{item['user_id']}:{item['filename']}:{item['commit_sha']}:{item['chunk_index']}"
        
        # Redis에 결과 저장 (임시)
        await self.redis_client.set(key, result, ex=86400)  # 24시간 유지
        
        # TODO: Supabase에 결과 저장 (실제 구현 필요)


class GitHubWebhookHandler:
    """GitHub 웹훅 처리를 담당하는 핸들러 클래스"""
    
    def __init__(self, supabase: AsyncClient, redis_client: Redis):
        self.supabase = supabase
        self.redis_client = redis_client
    
    async def handle_webhook(self, request: Request, background_tasks: BackgroundTasks) -> Dict:
        """메인 핸들러 함수: 웹훅 처리의 전체 흐름 관리"""
        try:
            # 1. 요청 데이터 추출 및 검증
            body_bytes, headers = await self._extract_request_data(request)
            signature = headers.get("X-Hub-Signature-256")
            if not signature:
                raise HTTPException(401, "Signature missing")
                
            # 2. 페이로드 파싱 및 저장소 정보 추출
            payload = self._parse_payload(body_bytes)
            owner, repo = self._extract_repo_info(payload)
            if not owner or not repo:
                return {"status": "success"}
                
            # 3. 웹훅 정보 조회 및 서명 검증
            webhook_rows = await self._get_active_webhooks(owner, repo)
            if not webhook_rows:
                return {"status": "success"}
                
            verified_row = await self._verify_signature(webhook_rows, body_bytes, signature)
            if not verified_row:
                raise HTTPException(401, "Invalid signature")
            
            # 4. 이벤트 유형에 따른 처리
            event_type = headers.get("X-GitHub-Event")
            if event_type == "push":
                await self._process_push_event(payload, verified_row, owner, repo, background_tasks)
            
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
        res = await self.supabase.table("db_webhooks") \
            .select("secret, learning_db_id, created_by") \
            .eq("repo_owner", owner) \
            .eq("repo_name", repo) \
            .eq("status", "active") \
            .execute()
            
        return res.data
    
    async def _verify_signature(self, webhook_rows: List[Dict], body_bytes: bytes, signature: str) -> Optional[Dict]:
        """서명 검증"""
        for row in webhook_rows:
            raw_secret = await GithubWebhookHelper.decrypt_secret(row["secret"])
            expected = "sha256=" + hmac.new(raw_secret.encode(), body_bytes, hashlib.sha256).hexdigest()
            if hmac.compare_digest(expected, signature):
                return row
                
        return None
    
    async def _process_push_event(self, payload: Dict, verified_row: Dict, owner: str, repo: str, background_tasks: BackgroundTasks):
        """푸시 이벤트 처리"""
        # 1. 커밋 정보 추출
        code_bundle = await GithubWebhookHelper.process_github_push_event(payload)
        
        # 2. GitHub 토큰 가져오기
        decrypted_pat = await get_integration_token(verified_row["created_by"], "github", self.supabase)
        github_service = GitHubWebhookService(token=decrypted_pat)
        
        # 3. 분석 서비스 초기화 및 백그라운드 작업 등록
        analysis_service = CodeAnalysisService(self.redis_client, self.supabase)
        
        # 4. 큐 처리 워커 시작 (백그라운드)
        background_tasks.add_task(self._start_queue_worker, analysis_service)
        
        # 5. 커밋별 파일 분석 작업 등록
        for commit in code_bundle:
            background_tasks.add_task(
                self._analyze_commit,
                github_service=github_service,
                analysis_service=analysis_service,
                owner=owner,
                repo=repo,
                commit_sha=commit["sha"],
                user_id=verified_row["created_by"]
            )
    
    async def _start_queue_worker(self, analysis_service: CodeAnalysisService):
        """분석 큐 처리 워커 시작"""
        await analysis_service.process_queue()
    
    async def _analyze_commit(self, github_service: GitHubWebhookService, analysis_service: CodeAnalysisService, 
                             owner: str, repo: str, commit_sha: str, user_id: str):
        """커밋 상세 정보 조회 및 분석"""
        try:
            # 커밋 상세 정보 조회
            commit_detail = await github_service.fetch_commit_detail(owner, repo, commit_sha)
            
            # 코드 변경 분석
            await analysis_service.analyze_code_changes(
                files=commit_detail["files"],
                owner=owner,
                repo=repo,
                commit_sha=commit_sha,
                user_id=user_id
            )
            
        except Exception as e:
            api_logger.error(f"커밋 분석 실패: {str(e)}")


@public_router.post("/webhook_operation")
async def handle_github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    supabase: AsyncClient = Depends(get_supabase),
    redis_client: Redis = Depends(get_redis)
):
    """GitHub 웹훅 이벤트 처리 엔드포인트"""
    handler = GitHubWebhookHandler(supabase, redis_client)
    return await handler.handle_webhook(request, background_tasks)