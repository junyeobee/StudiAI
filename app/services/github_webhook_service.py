from typing import Dict, List
import httpx
import secrets
from app.utils.logger import api_logger
from app.core.exceptions import GithubAPIError
from app.utils.retry import async_retry
from app.api.v1.endpoints.auth import require_user
from fastapi import Depends
class GitHubWebhookService:
    """GitHub 웹훅 관리 서비스"""
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }
        self.base_url = "https://api.github.com"
        
    @async_retry(max_retries=3, delay=1.0, backoff=2.0)
    async def create_webhook(self, repo_owner: str, repo_name: str, callback_url: str, 
                           events: List[str] = ["push"], secret: str = None) -> Dict:
        """
        GitHub 저장소에 웹훅 생성
        
        Args:
            repo_owner: 저장소 소유자
            repo_name: 저장소 이름
            callback_url: 웹훅 콜백 URL
            events: 구독할 이벤트 목록
            
        Returns:
            생성된 웹훅 정보
        """
        try:            
            # API 요청 URL
            api_url = f"{self.base_url}/repos/{repo_owner}/{repo_name}/hooks"
            
            # 웹훅 설정
            payload = {
                "name": "web",
                "active": True,
                "events": events,
                "config": {
                    "url": callback_url,
                    "content_type": "json",
                    "secret": secret,
                    "insecure_ssl": "0"
                }
            }
            
            # API 요청
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    api_url,
                    headers=self.headers,
                    json=payload,
                    timeout=30.0
                )
                
                # 응답 상태 코드 및 내용 로깅 (문제 해결용)
                api_logger.info(f"GitHub API 응답: {response.status_code}")
                
                response.raise_for_status()
                webhook_data = response.json()
                
                return {
                    "id": webhook_data["id"],
                    "events": webhook_data["events"],
                    "secret": secret
                }
                
        except httpx.HTTPStatusError as e:
            api_logger.error(f"GitHub 웹훅 생성 실패: HTTP {e.response.status_code} - {e.response.text}")
            raise GithubAPIError(f"웹훅 생성 실패: {e.response.text}")
        except Exception as e:
            api_logger.error(f"GitHub 웹훅 생성 중 예외 발생: {str(e)}")
            raise GithubAPIError(f"웹훅 생성 중 예외 발생: {str(e)}")
    
    async def list_repositories(self) -> List[Dict]:
        """사용자의 GitHub 저장소 목록 조회"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/user/repos",
                    headers=self.headers,
                    params={"per_page": 100, "sort": "updated"}
                )
                
                response.raise_for_status()
                repos = response.json()
                
                # 필요한 정보만 추출
                return [
                    {
                        "id": repo["id"],
                        "name": repo["name"],
                        "full_name": repo["full_name"],
                        "private": repo["private"],
                        "html_url": repo["html_url"],
                        "description": repo.get("description", "")
                    }
                    for repo in repos
                ]
                
        except Exception as e:
            api_logger.error(f"GitHub 저장소 목록 조회 실패: {str(e)}")
            raise GithubAPIError(f"저장소 목록 조회 실패: {str(e)}")
            
    async def delete_webhook(self, repo_owner: str, repo_name: str, webhook_id: int) -> bool:
        """GitHub 웹훅 삭제"""
        try:
            api_url = f"{self.base_url}/repos/{repo_owner}/{repo_name}/hooks/{webhook_id}"
            
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    api_url,
                    headers=self.headers,
                    timeout=30.0
                )
                
                return response.status_code == 204
                
        except Exception as e:
            api_logger.error(f"GitHub 웹훅 삭제 실패: {str(e)}")
            raise GithubAPIError(f"웹훅 삭제 실패: {str(e)}")
        
    @async_retry(max_retries=3, delay=1.0, backoff=2.0)
    async def fetch_commit_detail(self, owner, repo, sha):
        url = f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}"
        headers = {"Authorization": f"token {self.token}", "Accept": "application/vnd.github.v3+json"}
        try : 
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=15)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            api_logger.error(f"GitHub 커밋 상세 조회 실패: {str(e)}")
            raise GithubAPIError(f"커밋 상세 조회 실패: {str(e)}")
            
    @async_retry(max_retries=3, delay=1.0, backoff=2.0)
    async def fetch_file_content(self, owner: str, repo: str, path: str, ref: str = None) -> str:
        """
        GraphQL을 사용하여 GitHub 저장소에서 파일 전체 내용 가져오기
        
        Args:
            owner: 저장소 소유자
            repo: 저장소 이름
            path: 파일 경로
            ref: 커밋 SHA 또는 브랜치 이름 (기본값: 기본 브랜치)
            
        Returns:
            파일 전체 내용
        """
        try:
            # GraphQL 엔드포인트
            graphql_url = "https://api.github.com/graphql"
            
            # GraphQL 쿼리
            expression = f"{ref}:{path}" if ref else path
            query = """
            query ($owner: String!, $repo: String!, $expression: String!) {
              repository(owner: $owner, name: $repo) {
                object(expression: $expression) {
                  ... on Blob {
                    text
                  }
                }
              }
            }
            """
            
            variables = {
                "owner": owner,
                "repo": repo,
                "expression": expression
            }
            
            payload = {
                "query": query,
                "variables": variables
            }
            
            headers = {"Authorization": f"Bearer {self.token}"}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(graphql_url, json=payload, headers=headers, timeout=15)
                response.raise_for_status()
                result = response.json()
                
                # 결과 확인 및 파일 내용 추출
                if "errors" in result:
                    error_msg = result["errors"][0]["message"]
                    api_logger.error(f"GraphQL 요청 오류: {error_msg}")
                    raise GithubAPIError(f"파일 내용 조회 실패: {error_msg}")
                
                file_content = result.get("data", {}).get("repository", {}).get("object", {}).get("text")
                if file_content is None:
                    raise GithubAPIError(f"파일 내용이 없거나 파일을 찾을 수 없습니다: {path}")
                
                return file_content
                
        except Exception as e:
            api_logger.error(f"GitHub 파일 내용 조회 실패: {str(e)}")
            raise GithubAPIError(f"파일 내용 조회 실패: {str(e)}")
            
    @async_retry(max_retries=3, delay=1.0, backoff=2.0)
    async def fetch_reference_file(self, owner: str, repo: str, reference_path: str, ref: str = None) -> Dict:
        """
        참조 파일 내용 가져오기
        
        Args:
            owner: 저장소 소유자
            repo: 저장소 이름
            reference_path: 참조 파일 경로
            ref: 커밋 SHA 또는 브랜치 이름
            
        Returns:
            참조 파일 정보
        """
        try:
            content = await self.fetch_file_content(owner, repo, reference_path, ref)
            return {
                "path": reference_path,
                "content": content
            }
        except Exception as e:
            api_logger.error(f"참조 파일 조회 실패: {str(e)}")
            raise GithubAPIError(f"참조 파일 조회 실패: {str(e)}")
