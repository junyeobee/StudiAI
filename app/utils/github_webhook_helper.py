from Crypto.Cipher import AES
import base64
from Crypto.Random import get_random_bytes
import secrets
from app.core.config import settings
from typing import Tuple, Optional
import re
import httpx
class GithubWebhookHelper:
    @staticmethod
    async def parse_github_repo_url(repo_url: str) -> Tuple[Optional[str], Optional[str]]:
        """GitHub 저장소 URL에서 소유자와 저장소 이름 추출"""
        # owner/repo 추출
        pattern = r"github\.com/([^/]+)/([^/\.]+)"
        match = re.search(pattern, repo_url)
    
        if match:
            return match.group(1), match.group(2)
        return None, None

    @staticmethod
    async def encrypt_secret(raw_secret: str) -> str:
        """AES-256-GCM으로 암호화한 뒤 Base64 문자열 반환.

        반환 형식 = nonce(12B) + ciphertext + tag(16B) → Base64
        """
        key = base64.b64decode(settings.WEBHOOK_SECRET_KEY)
        nonce = get_random_bytes(12)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(raw_secret.encode())
        return base64.b64encode(nonce + ciphertext + tag).decode()

    @staticmethod
    async def decrypt_secret(token: str) -> str:
        """encrypt_secret() 결과를 평문으로 복호화한다."""
        key = base64.b64decode(settings.WEBHOOK_SECRET_KEY)
        raw = base64.b64decode(token)
        nonce, tag = raw[:12], raw[-16:]
        ciphertext = raw[12:-16]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)
        return plaintext.decode()

    @staticmethod
    async def generate_secret() -> str:
        """웹훅 HMAC 서명용 랜덤 시크릿 생성"""
        return secrets.token_hex(20)   # 40-char hex
    
    @staticmethod
    async def process_github_push_event(payload: dict):
        """Github 커밋 정보 추출"""
        try:
            commits = payload.get("commits", [])
            bundles = []
            for c in commits:
                bundles.append({
                    "sha": c["id"],
                    "message": c["message"],
                    "author": c["author"]["name"],
                    "files": {
                        "added":    c.get("added", []),
                        "modified": c.get("modified", []),
                        "removed":  c.get("removed", [])
                    }
                })
            return bundles        # 커밋 여러 개면 리스트 반환
        except Exception as e:
            print(f"푸시 이벤트 처리 중 오류: {str(e)}")

    @staticmethod
    async def strip_patch(patch: str) -> str:
        """
        diff → 수정된 코드만 남기고
        1) 메타줄 (diff/index/---/+++/@@) 제거
        2) + / - 접두어 제거
        3) 앞뒤 공백·탭 제거
        4) 완전히 빈 줄도 제거
        """
        cleaned = []
        for line in patch.splitlines():
            # ① 메타 줄 건너뛰기
            if line.startswith(("diff ", "index ", "--- ", "+++ ", "@@")):
                continue
            # ② + / - 접두어 제거
            if line[:1] in "+-":
                line = line[1:]
            # ③ 좌우 공백·탭 제거
            line = line.strip()
            # ④ 빈 줄 버리기
            if line:
                cleaned.append(line)
        return "".join(cleaned)
        

    