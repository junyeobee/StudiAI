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
    LearningSummary,
    LearningPagesRequest
)
from app.services.supa import (
    insert_learning_page
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

@router.get("/pages", response_model=List[LearningPlan])
async def get_learning_plans():
    """학습 계획 목록 조회"""
    try:
        plans = await notion_service.get_learning_plans()
        return plans
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pages/create")
async def create_pages(req: LearningPagesRequest):
    """
    여러 학습 페이지를 Notion에 생성하고,
    Supabase에 메타를 저장합니다.
    """
    results = []
    # 1) 현재 활성 DB는 notion_service.get_active_database() 등으로 가져와도 되고,
    #    req.learning_db_id가 이미 Supabase PK라면 그대로 사용하세요.
    notion_db_id = req.notion_db_id
    learning_db_id = str(req.notion_db_id)

    for plan in req.plans:
        try:
            # 2) Notion에 페이지 생성
            page_id = await notion_service.create_learning_page(notion_db_id, plan)

            # 3) AI 요약 블록 빈 문단 추가
            resp = await notion_service._make_request(
                "PATCH",
                f"blocks/{page_id}/children",
                json={
                    "children": [{
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {"rich_text":[{"text":{"content":""}}]}
                    }]
                }
            )
            ai_block_id = resp["results"][0]["id"]

            # 4) Supabase에 메타 저장 (priority/tags 없이)
            saved = await insert_learning_page(
                date=plan.date.isoformat(),
                title=plan.title,
                page_id=page_id,
                ai_block_id=ai_block_id,
                learning_db_id=learning_db_id
            )

            results.append({"page_id": page_id, "saved": saved})
        except Exception as e:
            results.append({"error": str(e), "plan": plan.dict()})

    return {
        "status": "completed",
        "total": len(req.plans),
        "results": results
    }

@router.get("/plans/{plan_id}", response_model=LearningPlan)
async def get_learning_plan(plan_id: str):
    """특정 학습 계획 조회"""
    try:
        plan = await notion_service.get_learning_plan(plan_id)
        return plan
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Learning plan not found: {str(e)}")

@router.post("/plans", response_model=LearningPlan)
async def create_learning_plan(plan: LearningPlanCreate):
    """새로운 학습 계획 생성"""
    try:
        new_plan = await notion_service.create_learning_plan(plan)
        return new_plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pages/summary")
def fill_summary(req: SummaryRequest):
    """요약 블록 내용 업데이트"""
    ai_block_id = notion_service.get_ai_block_id_by_page_id(req.page_id)
    if not ai_block_id:
        return { "error": "해당 페이지의 요약 블록 ID를 찾을 수 없습니다." }

    notion_service.update_ai_summary_block(ai_block_id, req.summary)
    return { "status": "updated" }

@router.post("/pages/summary", response_model=LearningSummary)
async def create_learning_summary(page_id: str, summary: str):
    """학습 요약 생성"""
    try:
        return await learning_service.create_learning_summary(page_id, summary)
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/page/summary/{page_id}", response_model=LearningSummary)
async def get_learning_summary(page_id: str):
    """학습 요약 조회"""
    try:
        summary = learning_service.get_learning_summary(page_id)
        if not summary:
            raise HTTPException(status_code=404, detail="학습 요약을 찾을 수 없습니다.")
        return summary
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e)) 

@router.delete("/plans/{plan_id}")
async def delete_learning_plan(plan_id: str):
    """학습 계획 삭제"""
    try:
        await notion_service.delete_learning_plan(plan_id)
        return {"message": "Learning plan deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.put("/pages/{plan_id}", response_model=LearningPlan)
async def update_learning_plan(plan_id: str, plan: LearningPlanUpdate):
    """학습 계획 수정"""
    try:
        updated_plan = await notion_service.update_learning_plan(plan_id, plan)
        return updated_plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))