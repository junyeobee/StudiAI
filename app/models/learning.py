"""
노션 페이지 생성/수정용 Pydantic 모델
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class LearningStatus(str, Enum):
    START_PRE = "시작 전"
    IN_PROGRESS = "진행중"
    COMPLETED = "완료"

# ────────────────── Create ──────────────────
class LearningPageCreate(BaseModel):
    """
    노션 페이지 생성 예시 (plans[*])

    {
      "title": "컴포넌트 기본 개념",
      "date":  "2025-04-29T09:00:00Z",
      "status": "시작 전",
      "revisit": false,
      "goal_intro": "컴포넌트가 뭔지 파악",
      "goals": ["JSX 이해", "props·state 차이 정리"],
      "summary": "AI요약 블록입니다."
    }
    """
    title: str
    date: datetime
    status: Optional[LearningStatus] = Field(None, description="진행 상태(시작 전, 진행중, 완료)")
    revisit: bool = Field(False, description="복습 여부")
    goal_intro: str
    goals: List[str]
    summary: str = Field("AI요약 블록입니다.", description="마크다운 형식으로 작성, 줄바꿈시 \\n 사용")

class LearningPagesRequest(BaseModel):
    """여러 페이지 일괄 생성 payload"""
    notion_db_id: str
    plans: List[LearningPageCreate]

# ────────────────── Update ──────────────────
class PagePropsUpdate(BaseModel):
    """페이지 기본 정보 업데이트"""
    title: Optional[str] = None
    date: Optional[datetime] = None
    status: Optional[LearningStatus] = None
    revisit: Optional[bool] = None

class ContentUpdate(BaseModel):
    """페이지 컨텐츠 업데이트"""
    goal_intro: Optional[str] = None
    goals: Optional[List[str]] = None

class SummaryUpdate(BaseModel):
    """페이지 요약 업데이트"""
    summary: str

class PageUpdateRequest(BaseModel):
    """
    노션 페이지 부분 업데이트 예시

    {
      "props": {
        "title": "새 제목",
        "status": "진행중"
      },
      "content": {
        "goal_intro": "이번엔 라이프사이클까지",
        "goals": ["라이프사이클 정리", "hook 기초"]
      },
      "summary": { "summary": "마크다운 형식으로 작성, 줄바꿈시 \\n 사용" }
    }
    """
    props: Optional[PagePropsUpdate] = None
    content: Optional[ContentUpdate] = None
    summary: Optional[SummaryUpdate] = None