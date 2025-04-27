"""
애플리케이션 설정
"""
from pydantic_settings import BaseSettings
from typing import List
from dotenv import load_dotenv
import os

# .env 파일 로드
load_dotenv()

# 디버그: 환경 변수 확인
print("NOTION_API_KEY:", os.getenv("NOTION_API_KEY"))
print("NOTION_PARENT_PAGE_ID:", os.getenv("NOTION_PARENT_PAGE_ID"))
print("SUPABASE_URL:", os.getenv("SUPABASE_URL"))
print("SUPABASE_KEY:", os.getenv("SUPABASE_KEY"))

class Settings(BaseSettings):
    # 프로젝트 정보
    PROJECT_NAME: str = "Notion Learning API"
    PROJECT_DESCRIPTION: str = "Notion을 활용한 학습 관리 API"
    VERSION: str = "1.0.0"
    
    # API 설정
    API_V1_STR: str = "/api/v1"
    
    # CORS 설정
    CORS_ORIGINS: List[str] = ["*"]
    
    # Notion API 설정
    NOTION_API_KEY: str
    NOTION_API_VERSION: str = "2022-06-28"
    NOTION_PARENT_PAGE_ID: str
    
    # Supabase 설정
    SUPABASE_URL: str
    SUPABASE_KEY: str
    
    # 웹훅 설정
    WEBHOOK_CREATE_URL: str
    WEBHOOK_DELETE_URL: str
    
    # 보안 설정
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # 로깅 설정
    LOG_LEVEL: str = "DEBUG"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings() 