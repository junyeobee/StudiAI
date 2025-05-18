# app/services/github_webhook_service.py
from typing import Dict, List, Optional, Tuple
import httpx
import secrets
from app.utils.logger import api_logger
from app.core.exceptions import GithubAPIError
from app.core.config import settings

class GitHubWebhookService:
    """GitHub 웹훅 직접 관리 서비스"""
    
    @staticmethod
    async def parse_github_repo_url(repo_url: str) -> Tuple[Optional[str], Optional[str]]:
        """GitHub 저장소 URL에서 소유자와 저장소 이름 추출"""
        import re
        # owner/repo 추출
        pattern = r"github\.com/([^/]+)/([^/\.]+)"
        match = re.search(pattern, repo_url)
        
        if match:
            return match.group(1), match.group(2)
        
        return None, None
    
    @staticmethod
    async def create_webhook_with_pat(repo_owner: str, repo_name: str, callback_url: str, 
                           personal_access_token: str,
                           events: List[str] = ["push"]) -> Dict:
        """
        개인 액세스 토큰(PAT)을 사용하여 GitHub 저장소에 웹훅 생성
        """
        try:
            # 웹훅 시크릿 생성
            webhook_secret = secrets.token_hex(20)
            
            # API 요청 URL
            api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/hooks"
            
            # 요청 헤더 (개인 액세스 토큰 사용)
            headers = {
                "Authorization": f"token {personal_access_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # 웹훅 설정
            payload = {
                "name": "web",
                "active": True,
                "events": events,
                "config": {
                    "url": callback_url,
                    "content_type": "json",
                    "secret": webhook_secret,
                    "insecure_ssl": "0"
                }
            }
            
            # API 요청
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    api_url,
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )
                
                # 응답 상태 코드 및 내용 로깅 (문제 해결용)
                api_logger.info(f"GitHub API 응답: {response.status_code} - {response.text}")
                
                response.raise_for_status()
                webhook_data = response.json()
                
                return {
                    "id": webhook_data["id"],
                    "events": webhook_data["events"],
                    "secret": webhook_secret
                }
                
        except httpx.HTTPStatusError as e:
            api_logger.error(f"GitHub 웹훅 생성 실패: HTTP {e.response.status_code} - {e.response.text}")
            raise GithubAPIError(f"웹훅 생성 실패: {e.response.text}")
        except Exception as e:
            api_logger.error(f"GitHub 웹훅 생성 중 예외 발생: {str(e)}")
            raise GithubAPIError(f"웹훅 생성 중 예외 발생: {str(e)}")