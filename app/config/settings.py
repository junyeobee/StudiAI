"""
Application settings and configuration
"""
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # API Settings
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Notion Learning Management System"
    
    # Notion Settings
    NOTION_API_KEY: str
    NOTION_API_VERSION: str = "2022-06-28"
    NOTION_PARENT_PAGE_ID: str
    
    # Supabase Settings
    SUPABASE_URL: str
    SUPABASE_KEY: str
    
    # Webhook Settings
    WEBHOOK_CREATE_URL: str
    WEBHOOK_DELETE_URL: str
    
    # Security
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings() 