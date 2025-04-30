"""
학습 DB의 하위 페이지 관련 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from app.services.notion_service import NotionService
from app.models.learning import (
    LearningPagesRequest,
    PageUpdateRequest
)
from app.services.supa import (
    insert_learning_page,
    get_used_notion_db_id,
    get_ai_block_id_by_page_id
)
from app.core.exceptions import DatabaseError
from app.utils.logger import api_logger

router = APIRouter()
notion_service = NotionService()

class PageRequest(BaseModel):
    db_title: str
    plans: list[dict]  # 여러 학습 계획 받아서 처리

class SummaryRequest(BaseModel):
    page_id: str
    summary: str

#현재 학습 중인 db 조회
@router.get("/pages/currentUsedDB")
async def list_all_learning_pages():
    """현재 학습 중인 db 조회"""
    try:
        db_id = await get_used_notion_db_id()
        if not db_id:
            raise HTTPException(404, "활성화된 학습 DB가 없습니다.")
        pages = await notion_service.list_all_pages(db_id)
        return {"db_id": db_id, "total": len(pages), "pages": pages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pages/create")
async def create_pages(req: LearningPagesRequest):
    notion_db_id = req.notion_db_id
    results = []

    for plan in req.plans:
        try:
            # 새로운 학습 행 생성
            page_id, ai_block_id = await notion_service.create_learning_page(notion_db_id, plan)

            # 생성된 학습 행에 대한 메타 저장
            saved = await insert_learning_page(
                date=plan.date.isoformat(),
                title=plan.title,
                page_id=page_id,
                ai_block_id=ai_block_id,
                learning_db_id=notion_db_id
            )

            results.append({"page_id": page_id, "ai_block_id": ai_block_id, "saved": saved})
        except Exception as e:
            results.append({"error": str(e), "plan": plan.model_dump()})

    return {
        "status": "completed",
        "total": len(req.plans),
        "results": results
    }

@router.patch("/pages/{page_id}")
async def patch_page(page_id: str, req: PageUpdateRequest):
    props = req.props.model_dump(by_alias=True) if req.props else None
    goal_intro = req.content.goal_intro if req.content else None
    goals = req.content.goals if req.content else None
    summary = req.summary.summary if req.summary else None
    if summary is not None:
        ai_block_id = await get_ai_block_id_by_page_id(page_id)
    else:
        ai_block_id = None
    
    await notion_service.update_learning_page_comprehensive(
        ai_block_id,
        page_id,
        props=props,
        goal_intro=goal_intro,
        goals=goals,
        summary=summary
    )
    return {"status":"success", "page_id": page_id}