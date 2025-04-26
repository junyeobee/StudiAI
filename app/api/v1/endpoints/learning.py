"""
학습 관련 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from app.services.learning_service import LearningService
from app.services.notion_service import NotionService
from app.models.learning import (
    LearningPlan,
    LearningPlanCreate,
    LearningPlanUpdate,
    LearningPlanResponse,
    LearningSummary
)
from app.core.exceptions import DatabaseError
from app.utils.logger import api_logger

router = APIRouter()
learning_service = LearningService()
notion_service = NotionService()

class PageRequest(BaseModel):
    db_title: str
    plans: list[dict]  # 여러 학습 계획 받아서 처리

class SummaryRequest(BaseModel):
    page_id: str
    summary: str

@router.post("/plans", response_model=LearningPlanResponse)
async def create_learning_plan(db_id: str, plan: LearningPlanCreate):
    """새로운 학습 계획 생성"""
    try:
        learning_plan = await learning_service.create_learning_plan(db_id, plan)
        return LearningPlanResponse(
            status="success",
            data=learning_plan,
            message="학습 계획이 성공적으로 생성되었습니다."
        )
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/plans/{page_id}", response_model=LearningPlanResponse)
async def update_learning_plan(page_id: str, plan: LearningPlanUpdate):
    """학습 계획 업데이트"""
    try:
        # 현재 학습 계획 조회
        current_plan = learning_service.get_learning_plan(page_id)
        if not current_plan:
            raise HTTPException(status_code=404, detail="학습 계획을 찾을 수 없습니다.")
        
        # 업데이트할 필드만 선택
        update_data = plan.dict(exclude_unset=True)
        
        # 학습 계획 업데이트
        updated_plan = LearningPlan(
            **current_plan.dict(),
            **update_data
        )
        
        learning_plan = await learning_service.update_learning_plan(page_id, updated_plan)
        return LearningPlanResponse(
            status="success",
            data=learning_plan,
            message="학습 계획이 성공적으로 업데이트되었습니다."
        )
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/plans/{page_id}", response_model=LearningPlanResponse)
async def get_learning_plan(page_id: str):
    """학습 계획 조회"""
    try:
        learning_plan = learning_service.get_learning_plan(page_id)
        if not learning_plan:
            raise HTTPException(status_code=404, detail="학습 계획을 찾을 수 없습니다.")
        
        return LearningPlanResponse(
            status="success",
            data=learning_plan,
            message="학습 계획을 성공적으로 조회했습니다."
        )
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/plans", response_model=List[LearningPlan])
async def list_learning_plans(db_id: str):
    """데이터베이스의 모든 학습 계획 조회"""
    try:
        return learning_service.get_learning_plans(db_id)
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pages/create")
def create_page(req: PageRequest):
    """학습 계획 페이지 생성"""
    notion_db_id, learning_db_id = notion_service.get_learning_database_by_title(req.db_title)
    if not notion_db_id or not learning_db_id:
        return { "error": "해당 제목의 DB를 찾을 수 없습니다." }

    notion_service.create_learning_pages(req.plans, notion_db_id, learning_db_id)
    return { "status": "created", "count": len(req.plans) }

@router.post("/pages/summary")
def fill_summary(req: SummaryRequest):
    """요약 블록 내용 업데이트"""
    ai_block_id = notion_service.get_ai_block_id_by_page_id(req.page_id)
    if not ai_block_id:
        return { "error": "해당 페이지의 요약 블록 ID를 찾을 수 없습니다." }

    notion_service.update_ai_summary_block(ai_block_id, req.summary)
    return { "status": "updated" }

@router.post("/summaries", response_model=LearningSummary)
async def create_learning_summary(page_id: str, summary: str):
    """학습 요약 생성"""
    try:
        return await learning_service.create_learning_summary(page_id, summary)
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/summaries/{page_id}", response_model=LearningSummary)
async def get_learning_summary(page_id: str):
    """학습 요약 조회"""
    try:
        summary = learning_service.get_learning_summary(page_id)
        if not summary:
            raise HTTPException(status_code=404, detail="학습 요약을 찾을 수 없습니다.")
        return summary
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e)) 