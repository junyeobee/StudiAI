"""
애플리케이션 설정
"""
import os
import re
from pydantic_settings import BaseSettings
from typing import List

# 1️⃣ GitHub Actions/GitLab CI 내장 변수에서 브랜치/태그 정보 추출
ref = os.getenv("GITHUB_REF") or os.getenv("CI_COMMIT_REF_NAME") or ""  
#   GITHUB_REF 예시: "refs/heads/release" 또는 "refs/tags/v1.0.0"

version = "dev"  # 기본값 (로컬 개발환경)

if ref.startswith("refs/tags/"):
    # 태그 푸시 이벤트: v1.0.0 → 1.0.0 추출
    m = re.match(r"refs/tags/v?(?P<ver>\d+\.\d+\.\d+)", ref)
    if m:
        version = m.group("ver")
elif ref.startswith("refs/heads/release"):
    # release 브랜치 → 항상 고정된 .env.release 로드
    version = "release"
    print(f"🚀 Release 브랜치 배포: {ref} → version={version}")
else:
    # 로컬 개발 또는 기타 브랜치
    print(f"🔧 개발환경: ref={ref} → version={version}")

class Settings(BaseSettings):
    # 프로젝트 정보 (동적 버전)
    PROJECT_NAME: str = "Notion Learning API"
    PROJECT_DESCRIPTION: str = "Notion을 활용한 학습 관리 API"
    APP_VERSION: str = version  # 🔄 동적 버전 설정
    
    # API 설정
    API_V1_STR: str = "/api/v1"
    
    # CORS 설정
    CORS_ORIGINS: List[str] = ["*"]
    
    # Notion API 설정
    NOTION_API_VERSION: str = "2022-06-28"
    NOTION_CLIENT_ID: str
    NOTION_CLIENT_SECRET: str
    NOTION_WEBHOOK_SECRET: str

    # Supabase 설정
    SUPABASE_URL: str
    SUPABASE_KEY: str
    
    # 웹훅 설정
    WEBHOOK_CREATE_URL: str
    WEBHOOK_DELETE_URL: str
    
    # Redis 설정
    REDIS_HOST: str
    REDIS_PORT: str
    REDIS_PASSWORD: str

    # GitHub OAuth
    GITHUB_CLIENT_ID: str
    GITHUB_SECRET_KEY: str
    
    # 보안 설정
    SECRET_KEY: str
    ENCRYPTION_KEY: str
    WEBHOOK_SECRET_KEY: str
    API_BASE_URL: str

    # API Key
    OPENAI_API_KEY: str  # 🔧 OPENAI_KEY → OPENAI_API_KEY로 통일

    # 로깅 설정
    LOG_LEVEL: str = "DEBUG"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    class Config:
        env_file = f"app/core/.env.{version}"  # 🎯 동적 환경파일 선택
        case_sensitive = True

# 설정 인스턴스 생성
settings = Settings()

# 🚀 시작시 설정 정보 출력
print(f"📋 환경설정 로드: .env.{version} (APP_VERSION: {settings.APP_VERSION})")
