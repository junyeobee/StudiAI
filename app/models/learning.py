"""
학습 관련 Pydantic 모델
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class LearningStatus(str, Enum):
    START_PRE = "시작 전"
    IN_PROGRESS = "진행중"
    COMPLETED = "완료"

class LearningPlan(BaseModel):
    """학습 계획 (Notion DB 단위)"""
    page_id: str = Field(..., description="Notion 페이지 ID")
    db_id: str = Field(..., description="Notion 데이터베이스 ID")
    title: str = Field(..., description="학습 계획 제목")
    description: Optional[str] = Field(None, description="학습 계획 설명")
    status: LearningStatus = Field(default=LearningStatus.START_PRE, description="학습 상태")
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
    """학습 계획 응답 래퍼"""
    status: str = Field(..., description="응답 상태")
    data: LearningPlan = Field(..., description="학습 계획 정보")
    message: str = Field(..., description="응답 메시지")


# -----------------------------------------------
# 하위 페이지(학습 페이지) 생성용 모델
# -----------------------------------------------
class LearningPageCreate(BaseModel):
    """단일 학습 페이지 생성 정보 (Notion DB 속성에 맞춤)"""
    title: str = Field(..., description="학습 제목")
    date:  datetime = Field(..., description="학습 날짜")
    status: LearningStatus = Field(LearningStatus.START_PRE, description="진행 상태")
    revisit: bool = Field(False, alias="복습 여부", description="복습 여부 (checkbox)")

class LearningPagesRequest(BaseModel):
    """여러 학습 페이지 일괄 생성 요청"""
    notion_db_id: str = Field(..., description="Notion 데이터베이스 ID")
    plans: List[LearningPageCreate] = Field(..., description="생성할 학습 페이지 리스트")