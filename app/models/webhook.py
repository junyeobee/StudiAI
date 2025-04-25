"""
웹훅 관련 Pydantic 모델
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

class WebhookStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"

class WebhookInfo(BaseModel):
    """웹훅 기본 정보"""
    db_id: str = Field(..., description="Notion 데이터베이스 ID")
    webhook_id: str = Field(..., description="웹훅 ID")
    status: WebhookStatus = Field(default=WebhookStatus.INACTIVE, description="웹훅 상태")
    created_at: datetime = Field(default_factory=datetime.now, description="생성 일시")
    last_triggered_at: Optional[datetime] = Field(None, description="마지막 트리거 일시")

class WebhookCreate(BaseModel):
    """웹훅 생성 요청"""
    db_id: str = Field(..., description="Notion 데이터베이스 ID")

class WebhookUpdate(BaseModel):
    """웹훅 업데이트 요청"""
    status: Optional[WebhookStatus] = Field(None, description="웹훅 상태")

class WebhookEvent(BaseModel):
    """웹훅 이벤트"""
    event_type: str = Field(..., description="이벤트 타입")
    db_id: str = Field(..., description="Notion 데이터베이스 ID")
    page_id: str = Field(..., description="페이지 ID")
    payload: Dict[str, Any] = Field(..., description="이벤트 페이로드")
    timestamp: datetime = Field(default_factory=datetime.now, description="이벤트 발생 일시")

class WebhookResponse(BaseModel):
    """웹훅 응답"""
    status: str = Field(..., description="응답 상태")
    data: Optional[WebhookInfo] = Field(None, description="웹훅 정보")
    message: str = Field(..., description="응답 메시지") 