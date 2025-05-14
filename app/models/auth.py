from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from typing import List, Dict

class UserIntegrationRequest(BaseModel):
    """사용자 통합 요청"""
    id: Optional[str] = Field(None, description="통합 ID (업데이트 시 사용)")
    user_id: str = Field(..., description="사용자 ID")
    provider: str = Field(..., description="서비스 제공자 (github, notion 등)")
    access_token: str = Field(..., description="접근 토큰")
    refresh_token: Optional[str] = Field(None, description="리프레시 토큰")
    scopes: Optional[List[str]] = Field(None, description="권한 범위")
    created_at: Optional[datetime] = Field(None, description="생성 시간, 업데이트 시")
    expires_in: Optional[int] = Field(None, description="만료 시간(초)")

class UserIntegration(BaseModel):
    id: Optional[str] = Field(None, description="db아이디, 업데이트시 포함")
    user_id: str = Field(..., description="사용자 ID")
    provider: str = Field(..., description="서비스 제공자")
    access_token: str = Field(..., description="접근 토큰")
    refresh_token: Optional[str] = Field(None, description="리프레시 토큰")
    scopes: Optional[List[str]] = Field(None, description="권한 범위")
    expires_at: Optional[datetime] = Field(None, description="만료 시간")
    created_at: datetime = Field(..., description="생성 시간")
    updated_at: datetime = Field(..., description="업데이트 시간")
    token_iv: Optional[str] = Field(None, description="토큰 IV")

class UserIntegrationResponse(BaseModel):
    """사용자 통합 응답"""
    id: str = Field(..., description="통합 ID")
    provider: str = Field(..., description="서비스 제공자")
    user_id: str = Field(..., description="사용자 ID")
    scopes: Optional[List[str]] = Field(None, description="권한 범위")
    expires_at: Optional[datetime] = Field(None, description="만료 시간")
    created_at: datetime = Field(..., description="생성 시간")
    updated_at: datetime = Field(..., description="업데이트 시간")

class ApiKeyResponse(BaseModel):
    key: str

class ApiKeyList(BaseModel):
    keys: List[Dict]

class MessageResponse(BaseModel):
    message: str
    success: bool