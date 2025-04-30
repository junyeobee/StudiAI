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

class LearningPageCreate(BaseModel):
    """단일 학습 페이지 생성 정보 (Notion DB 속성에 맞춤)"""
    title: str = Field(..., description="학습 제목")
    date:  datetime = Field(..., description="학습 날짜")
    status: LearningStatus = Field(LearningStatus.START_PRE, description="진행 상태")
    revisit: bool = Field(False, alias="복습 여부", description="복습 여부 (checkbox)")
    goal_intro: str = Field("이 섹션에 학습의 목적이나 계획을 간단히 작성하세요." ,description="학습 목표 섹션 상단에 들어갈 인용문")
    goals: List[str] = Field(..., description="학습 목표")
    summary: str = Field(..., description="학습 요약")

class LearningPagesRequest(BaseModel):
    """여러 학습 페이지 일괄 생성 요청"""
    notion_db_id: str = Field(..., description="Notion 데이터베이스 ID")
    plans: List[LearningPageCreate] = Field(..., description="생성할 학습 페이지 리스트")

class PagePropsUpdate(BaseModel):
    title: Optional[str] = Field(None, description="학습 제목")
    date: Optional[datetime] = Field(None, description="학습 날짜")
    status: Optional[LearningStatus] = Field(None, alias="진행 상태", description="진행 상태")
    revisit: Optional[bool] = Field(None, alias="복습 여부", description="복습 여부")

class ContentUpdate(BaseModel):
    goal_intro: Optional[str] = Field(None, description="목표 인용문")
    goals: Optional[List[str]] = Field(None, description="학습 목표 리스트")

class SummaryUpdate(BaseModel):
    summary: str = Field(..., description="AI 요약 블록 텍스트")

class PageUpdateRequest(BaseModel):
    props: Optional[PagePropsUpdate] = None
    content: Optional[ContentUpdate] = None
    summary: Optional[SummaryUpdate] = None
