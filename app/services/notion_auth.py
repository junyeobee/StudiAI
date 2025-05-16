from app.utils.logger import notion_logger
from app.core.exceptions import NotionAPIError
import httpx
import base64
from app.core.config import settings

class NotionAuthService:
    # 토큰 발급 후 교환 요청 메소드
    #[참고] AsyncClient 사용 시 비동기 처리 가능
    #{말투는 이렇게 해주세요}
    async def exchange_code_for_token(self, code: str) -> dict:
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
                    # api 주소 변경 -> localhost:8000 -> 실제 주소로 변경
                    "redirect_uri": "http://localhost:8000/auth_public/callback/notion"
                }
                res = await client.post("https://api.notion.com/v1/oauth/token", headers=headers, json=body)
                return res.json()
        except Exception as e:
            notion_logger.error(f"토큰 교환 실패: {str(e)}")
            raise NotionAPIError(f"토큰 교환 실패: {str(e)}")