from typing import Dict, List
import httpx
import secrets
from app.utils.logger import api_logger
from app.core.exceptions import GithubAPIError
from app.utils.retry import async_retry


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
