"""
학습 관련 Pydantic 모델
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class LearningStatus(str, Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class LearningPlan(BaseModel):
    """학습 계획"""
    page_id: str = Field(..., description="Notion 페이지 ID")
    db_id: str = Field(..., description="Notion 데이터베이스 ID")
    title: str = Field(..., description="학습 계획 제목")
    description: Optional[str] = Field(None, description="학습 계획 설명")
    status: LearningStatus = Field(default=LearningStatus.PLANNED, description="학습 상태")
    start_date: Optional[datetime] = Field(None, description="시작 일시")
    end_date: Optional[datetime] = Field(None, description="종료 일시")
    created_at: datetime = Field(default_factory=datetime.now, description="생성 일시")
    updated_at: datetime = Field(default_factory=datetime.now, description="수정 일시")

class LearningPlanCreate(BaseModel):
    """학습 계획 생성 요청"""
    title: str = Field(..., description="학습 계획 제목")
    description: Optional[str] = Field(None, description="학습 계획 설명")
    start_date: Optional[datetime] = Field(None, description="시작 일시")
    end_date: Optional[datetime] = Field(None, description="종료 일시")

class LearningPlanUpdate(BaseModel):
    """학습 계획 업데이트 요청"""
    title: Optional[str] = Field(None, description="학습 계획 제목")
    description: Optional[str] = Field(None, description="학습 계획 설명")
    status: Optional[LearningStatus] = Field(None, description="학습 상태")
    start_date: Optional[datetime] = Field(None, description="시작 일시")
    end_date: Optional[datetime] = Field(None, description="종료 일시")

class LearningSummary(BaseModel):
    """학습 요약"""
    page_id: str = Field(..., description="Notion 페이지 ID")
    summary: str = Field(..., description="학습 요약 내용")
    created_at: datetime = Field(default_factory=datetime.now, description="생성 일시")
    updated_at: datetime = Field(default_factory=datetime.now, description="수정 일시")

class LearningPlanResponse(BaseModel):
    """학습 계획 응답"""
    status: str = Field(..., description="응답 상태")
    data: LearningPlan = Field(..., description="학습 계획 정보")
    message: str = Field(..., description="응답 메시지") 