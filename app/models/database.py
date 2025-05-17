"""
노션DB 관련 Pydantic 모델
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


class DatabaseStatus(str, Enum):
    """학습 DB 상태"""
    READY = "ready"  # 초기 생성・대기 상태
    USED = "used"  # 현재 학습에 사용 중
    END = "end"  # 학습 종료


class WebhookStatus(str, Enum):
    """웹훅 상태"""
    ACTIVE = "active"  # 정상 동작
    INACTIVE = "inactive"  # 비활성 / 모니터링 중지
    PENDING = "pending"  # 생성 대기 or 확인 대기
    FAILED = "failed"  # 오류 발생


class DatabaseInfo(BaseModel):
    """노션DB 기본 정보"""
    db_id: str = Field(..., description="Notion DB ID")
    title: str = Field(..., description="DB 제목")
    parent_page_id: str = Field(..., description="상위 페이지 ID")
    status: DatabaseStatus = Field(DatabaseStatus.READY, description="DB 상태 (ready / used / end)")
    webhook_id: Optional[str] = Field(None, description="웹훅 ID")
    webhook_status: Optional[WebhookStatus] = Field(None, description="웹훅 상태 (active / inactive / pending / failed)")
    last_used_date: Optional[datetime] = Field(None, description="마지막 사용 일시")
    workspace_id: Optional[str] = Field(None, description="워크스페이스 ID")


class DatabaseCreate(BaseModel):
    """새 DB 생성 요청"""
    title: str = Field(..., description="DB 제목")


class DatabaseUpdate(BaseModel):
    """DB 정보 부분 업데이트 요청 (None 값은 무시)"""
    db_id: Optional[str] = Field(None, description="Notion DB ID")
    title: Optional[str] = Field(None, description="DB 제목")
    parent_page_id: Optional[str] = Field(None, description="상위 페이지 ID")
    status: Optional[DatabaseStatus] = Field(None, description="DB 상태 (ready / used / end)")
    webhook_id: Optional[str] = Field(None, description="웹훅 ID")
    webhook_status: Optional[WebhookStatus] = Field(None, description="웹훅 상태 (active / inactive / pending / failed)")
    last_used_date: Optional[datetime] = Field(None, description="마지막 사용 일시")
    workspace_id: Optional[str] = Field(None, description="워크스페이스 ID")

    def dict(self, **kwargs):
        """`None` 값을 제외한 dict 반환"""
        return {k: v for k, v in super().dump(**kwargs).items() if v is not None}


class DatabaseResponse(BaseModel):
    """공통 API 응답 래퍼"""
    status: str = Field(..., description="응답 상태")
    data: DatabaseInfo = Field(..., description="데이터베이스 정보")
    message: str = Field(..., description="응답 메시지")


class DatabaseMetadata(BaseModel):
    """Notion 페이지 안에서 발견된 **하위 DB** 메타"""
    id: str = Field(..., description="child_database 블록 ID (DB ID)")
    title: str = Field(..., description="데이터베이스 제목")
