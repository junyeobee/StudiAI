"""
학습 DB의 하위 페이지 관련 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from app.services.notion_service import NotionService
from app.models.learning import (
    LearningPagesRequest,
    PageUpdateRequest
)
from app.services.supa import (
    insert_learning_page,
    get_used_notion_db_id,
    get_ai_block_id_by_page_id,
    delete_learning_page
)
from app.utils.logger import api_logger
from app.utils.notion_utils import(
    block_content,
    serialize_page_props
)
import redis
from app.core.supabase_connect import get_supabase
from supabase._async.client import AsyncClient
from fastapi import Depends
from app.api.v1.dependencies.auth import require_user
from app.api.v1.dependencies.notion import get_notion_service
from app.utils.logger import api_logger
from app.core.redis_connect import get_redis

router = APIRouter()

@router.get("/pages")
async def list_learning_pages(redis: redis.Redis = Depends(get_redis),user_id:str = Depends(require_user), current: bool = False, db_id: str | None = None, supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service)):
    """
    학습 페이지 목록 조회
    - current=true : 현재 used DB 기준
    - db_id=<uuid> : 특정 DB 기준
    둘 다 지정시 db_id 결과
    """
    try:
        target_db_id = db_id
        if not target_db_id:
            if current:
                target_db_id = await get_used_notion_db_id(supabase, user_id)
            else:
                api_logger.error("학습 페이지 목록 조회 실패: db_id 또는 current=true 중 하나는 필수입니다.")
                raise HTTPException(400, "db_id 또는 current=true 중 하나는 필수입니다.")

        if not target_db_id:
            api_logger.error("학습 페이지 목록 조회 실패: 활성화된 학습 DB가 없습니다.")
            raise HTTPException(404, "활성화된 학습 DB가 없습니다.")

        pages = await notion_service.list_all_pages(target_db_id)
        return {
            "db_id": target_db_id,
            "total": len(pages),
            "pages": pages
        }

    except HTTPException:
        raise
    except Exception as e:
        api_logger.error(f"학습 페이지 목록 조회 실패: {str(e)}")
        raise HTTPException(500, str(e))

@router.post("/pages/create")
async def create_pages(req: LearningPagesRequest, supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service)):
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
                learning_db_id=notion_db_id,
                supabase=supabase
            )

            results.append({"page_id": page_id, "ai_block_id": ai_block_id, "saved": saved})
        except Exception as e:
            api_logger.error(f"학습 페이지 생성 실패: {str(e)}")
            results.append({"error": str(e), "plan": plan.model_dump()})

    return {
        "status": "completed",
        "total": len(req.plans),
        "results": results
    }

@router.patch("/pages/{page_id}")
async def patch_page(page_id: str, req: PageUpdateRequest, supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service)):
    print(req)
    payload = jsonable_encoder(req, by_alias=True, exclude_none=True)
    props = payload.get("props")
    content = payload.get("content")
    summary = payload.get("summary").get("summary") if payload.get("summary") else None
    
    if summary is not None:
        ai_block_id = await get_ai_block_id_by_page_id(page_id, supabase)
    else:
        ai_block_id = None
    
    if props is not None:
        props = serialize_page_props(props)
    try:
        await notion_service.update_learning_page_comprehensive(
            ai_block_id,
            page_id,
            props=props if props else None,
            goal_intro=content.get("goal_intro") if content else None,
            goals=content.get("goals") if content else None,
            summary=summary
        )
        return {"status":"success", "page_id": page_id}
    except Exception as e:
        api_logger.error(f"학습 페이지 업데이트 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))



# 완료
@router.get("/pages/{page_id}/content")
async def get_content(page_id: str, notion_service: NotionService = Depends(get_notion_service)):
    try:
        data = await notion_service.get_page_content(page_id)
        print(data)
        blocks = [block_content(b) for b in data["blocks"]]
        return blocks
    except Exception as e:
        api_logger.error(f"학습 페이지 콘텐츠 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    

# 페이지 삭제
@router.delete("/pages/{page_id}")
async def delete_page(page_id: str, supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service)):
    try:
        await notion_service.delete_page(page_id)
        await delete_learning_page(page_id, supabase)
        return {"status": "deleted", "page_id": page_id}
    except Exception as e:
        api_logger.error(f"학습 페이지 삭제 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
