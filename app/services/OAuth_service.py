from app.core.exceptions import NotionAPIError
import httpx
import base64
from app.core.config import settings
from app.core.exceptions import GithubAPIError
from app.utils.logger import api_logger

class OAuthService:
    # 토큰 발급 후 교환 요청 메소드
    #[참고] AsyncClient 사용 시 비동기 처리 가능
    #{말투는 이렇게 해주세요}
    async def exchange_notion_code(self, code: str) -> dict:
        try : 
            async with httpx.AsyncClient() as client:
                auth = base64.b64encode(f"{settings.NOTION_CLIENT_ID}:{settings.NOTION_CLIENT_SECRET}".encode()).decode()
                headers = {
                    "Authorization": f"Basic {auth}",
                    "Content-Type": "application/json"
                }
                body = {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": f"{settings.API_BASE_URL}/auth_public/callback/notion"
                }
                res = await client.post("https://api.notion.com/v1/oauth/token", headers=headers, json=body)
                return res.json()
        except Exception as e:
            api_logger.error(f"토큰 교환 실패: {str(e)}")
            raise NotionAPIError(f"토큰 교환 실패: {str(e)}")
        
    async def exchange_github_code(self, code: str) -> dict:
        """GitHub OAuth 코드를 토큰으로 교환"""
        try:
            async with httpx.AsyncClient() as client:
                body = {
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_SECRET_KEY,
                    "code": code,
                    "redirect_uri": f"{settings.API_BASE_URL}/auth_public/callback/github"
                }
                headers = {
                    "Accept": "application/json"
                }
                res = await client.post(
                    "https://github.com/login/oauth/access_token", 
                    headers=headers,
                    json=body
                )
                return res.json()
        except Exception as e:
            api_logger.error(f"GitHub 토큰 교환 실패: {str(e)}")
            raise GithubAPIError(f"토큰 교환 실패: {str(e)}")