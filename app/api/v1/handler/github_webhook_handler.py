from fastapi import HTTPException, Request, BackgroundTasks
from app.utils.github_webhook_helper import GithubWebhookHelper
from app.services.github_webhook_service import GitHubWebhookService
from app.services.auth_service import get_integration_token
from app.services.code_analysis_service import CodeAnalysisService
from redis.asyncio import Redis
from app.services.supa import get_active_webhooks
from supabase._async.client import AsyncClient
from typing import Dict, List, Optional, Tuple
from app.utils.logger import api_logger
import json
import hmac
import hashlib
import asyncio

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
    
    async def _process_push_event(self, payload: Dict, verified_row: Dict, owner: str, repo: str, background_tasks: BackgroundTasks):
        """푸시 이벤트 처리"""
        # 1. 커밋 정보 추출
        code_bundle = await GithubWebhookHelper.process_github_push_event(payload)
        print(code_bundle)
        
        # 2. GitHub 토큰 가져오기
        decrypted_pat = await get_integration_token(verified_row["created_by"], "github", self.supabase)
        github_service = GitHubWebhookService(token=decrypted_pat)
        
        # 3. 분석 서비스 초기화 및 백그라운드 작업 등록
        analysis_service = CodeAnalysisService(self.redis_client, self.supabase)
        
        # 3.1 참조 파일 가져오기 서비스 핸들러 등록
        self._register_reference_file_handler(github_service, owner, repo, verified_row["created_by"])
        
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
            
    def _register_reference_file_handler(self, github_service: GitHubWebhookService, owner: str, repo: str, user_id: str):
        """참조 파일 가져오기 서비스 등록"""
        # 비동기 PubSub 대신 키-값 기반 처리 방식 사용
        
        # 참조 파일 키 접두사 설정
        reference_key_prefix = f"ref_request:{owner}:{repo}:{user_id}:"
        response_key_prefix = f"ref_response:{owner}:{repo}:{user_id}:"
        
        # 참조 파일 요청 폴링 태스크
        async def poll_reference_requests():
            """주기적으로 참조 파일 요청 확인"""
            try:
                while True:
                    # 요청 키 패턴으로 검색
                    request_keys = self.redis_client.keys(f"{reference_key_prefix}*")
                    
                    for key in request_keys:
                        try:
                            # 요청 데이터 가져오기
                            request_data_str = self.redis_client.get(key)
                            if not request_data_str:
                                continue
                                
                            # 요청 처리
                            request_data = json.loads(request_data_str)
                            reference_path = request_data.get('path')
                            commit_sha = request_data.get('commit_sha', 'HEAD')
                            request_id = request_data.get('request_id')
                            
                            if not reference_path or not request_id:
                                continue
                            
                            # 이미 처리 중인지 확인
                            processing_key = f"{reference_key_prefix}processing:{request_id}"
                            if self.redis_client.exists(processing_key):
                                continue
                                
                            # 처리 중 표시
                            self.redis_client.setex(processing_key, 60, "1")  # 1분 타임아웃
                            
                            # 요청 키 삭제
                            self.redis_client.delete(key)
                            
                            # GitHub API로 파일 가져오기
                            try:
                                file_content = await github_service.fetch_file_content(
                                    owner=owner,
                                    repo=repo,
                                    path=reference_path,
                                    ref=commit_sha
                                )
                                
                                # 응답 저장
                                response = {
                                    'path': reference_path,
                                    'content': file_content,
                                    'status': 'success'
                                }
                            except Exception as e:
                                response = {
                                    'path': reference_path,
                                    'error': str(e),
                                    'status': 'error'
                                }
                            
                            # 응답 저장
                            response_key = f"{response_key_prefix}{request_id}"
                            self.redis_client.setex(
                                response_key, 
                                300,  # 5분 유효
                                json.dumps(response)
                            )
                            
                            # 처리 완료 표시 삭제
                            self.redis_client.delete(processing_key)
                            
                            api_logger.info(f"참조 파일 '{reference_path}' 처리 완료: {response['status']}")
                            
                        except Exception as e:
                            api_logger.error(f"참조 파일 처리 오류: {str(e)}")
                    
                    await asyncio.sleep(1)
            except Exception as e:
                api_logger.error(f"참조 파일 폴링 오류: {str(e)}")
        
        # 폴링 태스크 시작
        asyncio.create_task(poll_reference_requests())
    
    async def _start_queue_worker(self, analysis_service: CodeAnalysisService):
        """분석 큐 처리 워커 시작"""
        await analysis_service.process_queue()
    
    async def _analyze_commit(self, github_service: GitHubWebhookService, analysis_service: CodeAnalysisService, 
                             owner: str, repo: str, commit_sha: str, user_id: str):
        """커밋 상세 정보 조회 및 분석"""
        try:
            # 커밋 상세 정보 조회
            commit_detail = await github_service.fetch_commit_detail(owner, repo, commit_sha)
            
            # 수정된 파일들에 대해 전체 내용 가져오기
            files = commit_detail.get("files", [])
            for file in files:
                status = file.get("status", "")
                filename = file.get("filename", "")
                
                # 파일이 수정된 경우에만 전체 내용 가져오기 필요
                if status == "modified" and "patch" in file:
                    try:
                        # GraphQL로 파일 전체 내용 가져오기
                        file_content = await github_service.fetch_file_content(
                            owner=owner,
                            repo=repo,
                            path=filename,
                            ref=commit_sha
                        )
                        
                        # 전체 파일 내용 추가
                        file["full_content"] = file_content
                        api_logger.info(f"파일 '{filename}' 전체 내용 가져옴 (길이: {len(file_content)})")
                    except Exception as e:
                        api_logger.error(f"파일 '{filename}' 전체 내용 가져오기 실패: {str(e)}")
                
                # 추가된 파일의 경우 patch가 전체 내용이므로 full_content 별도 설정
                elif status == "added" and "patch" in file:
                    file["full_content"] = file["patch"]
            
            # 코드 변경 분석
            await analysis_service.analyze_code_changes(
                files=files,
                owner=owner,
                repo=repo,
                commit_sha=commit_sha,
                user_id=user_id
            )
            
        except Exception as e:
            api_logger.error(f"커밋 분석 실패: {str(e)}")