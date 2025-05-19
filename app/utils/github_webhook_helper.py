from Crypto.Cipher import AES
import base64
from Crypto.Random import get_random_bytes
import secrets
from app.core.config import settings
from typing import Tuple, Optional
import re

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
    
    async def process_github_push_event(payload: dict, webhook: dict):
        """GitHub 푸시 이벤트 처리 함수 (단순 로깅만 수행)"""
        try:
            # 웹훅 정보 추출
            learning_db_id = webhook.get("learning_db_id")
            
            # 커밋 정보 출력
            print("===== GitHub 푸시 이벤트 처리 =====")
            print(f"학습 DB ID: {learning_db_id}")
            
            # 커밋 정보 추출 및 출력
            commits = payload.get("commits", [])
            print(f"커밋 수: {len(commits)}")
            
            for i, commit in enumerate(commits):
                print(f"\n커밋 #{i+1}:")
                print(f"ID: {commit.get('id')}")
                print(f"메시지: {commit.get('message')}")
                print(f"작성자: {commit.get('author', {}).get('name')}")
                print(f"추가 파일: {commit.get('added', [])}")
                print(f"수정 파일: {commit.get('modified', [])}")
                print(f"삭제 파일: {commit.get('removed', [])}")
            
            print("===== 푸시 이벤트 처리 완료 =====")
            
        except Exception as e:
            print(f"푸시 이벤트 처리 중 오류: {str(e)}")