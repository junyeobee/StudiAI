from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class RegisterRequest(BaseModel):
    """사용자 등록 요청"""
    user_id: str = Field(..., description="사용자 식별자 (이메일 권장)")

class RegisterResponse(BaseModel):
    """사용자 등록 응답"""
    auth_token: str = Field(..., description="인증 토큰")
    
class UserIntegrationRequest(BaseModel):
    """사용자 통합 요청"""
    provider: str = Field(..., description="서비스 제공자 (github, notion 등)")
    access_token: str = Field(..., description="접근 토큰")
    refresh_token: Optional[str] = Field(None, description="갱신 토큰 (선택)")
    scopes: Optional[list[str]] = Field(None, description="권한 범위")
    expires_at: Optional[datetime] = Field(None, description="만료 시간")

class UserIntegrationResponse(BaseModel):
    """사용자 통합 응답"""
    id: str = Field(..., description="통합 ID")
    provider: str = Field(..., description="서비스 제공자")
    user_id: str = Field(..., description="사용자 ID")
    scopes: Optional[list[str]] = Field(None, description="권한 범위")
    expires_at: Optional[datetime] = Field(None, description="만료 시간")
    created_at: datetime = Field(..., description="생성 시간")
    updated_at: datetime = Field(..., description="업데이트 시간")