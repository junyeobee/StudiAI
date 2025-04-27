"""
데이터베이스 관련 Pydantic 모델
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum

class DatabaseStatus(str, Enum):
    READY = "ready"
    USED = "used"
    END = "end"

class WebhookStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    FAILED = "failed"

class DatabaseInfo(BaseModel):
    """데이터베이스 기본 정보"""
    db_id: str = Field(..., description="Notion 데이터베이스 ID")
    title: str = Field(..., description="데이터베이스 제목")
    parent_page_id: str = Field(..., description="상위 페이지 ID")
    status: DatabaseStatus = Field(default=DatabaseStatus.READY, description="데이터베이스 상태")
    webhook_id: Optional[str] = Field(None, description="웹훅 ID")
    webhook_status: Optional[str] = Field(None, description="웹훅 상태")
    last_used_date: Optional[datetime] = Field(None, description="마지막 사용 일시")

class DatabaseCreate(BaseModel):
    """데이터베이스 생성 요청"""
    title: str = Field(..., description="데이터베이스 제목")

class DatabaseUpdate(BaseModel):
    """데이터베이스 업데이트 요청"""
    db_id: Optional[str] = None
    title: Optional[str] = None
    parent_page_id: Optional[str] = None
    status: Optional[DatabaseStatus] = None
    webhook_id: Optional[str] = None
    webhook_status: Optional[WebhookStatus] = None
    last_used_date: Optional[datetime] = None

    def dict(self, **kwargs):
        # None이 아닌 값만 포함
        return {k: v for k, v in super().dict(**kwargs).items() if v is not None}

class DatabaseResponse(BaseModel):
    """데이터베이스 응답"""
    status: str = Field(..., description="응답 상태")
    data: DatabaseInfo = Field(..., description="데이터베이스 정보")
    message: str = Field(..., description="응답 메시지") 

class DatabaseMetadata(BaseModel):
    """페이지 안의 모든 db조회"""
    id: str = Field(..., description="child_database 블록의 ID (해당 데이터베이스 ID)")
    title: str = Field(..., description="데이터베이스 제목")