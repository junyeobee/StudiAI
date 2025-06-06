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
    delete_learning_page,
    list_all_learning_databases,
    get_default_workspace
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
from app.api.v1.dependencies.workspace import get_user_workspace_with_fallback
from app.api.v1.dependencies.notion import get_notion_service
from app.utils.logger import api_logger
from app.core.redis_connect import get_redis
from app.services.redis_service import RedisService
from app.services.workspace_cache_service import workspace_cache_service

router = APIRouter()
redis_service = RedisService()

@router.get("/pages")
async def list_learning_pages(workspace_id: str = Depends(get_user_workspace_with_fallback), redis: redis.Redis = Depends(get_redis), current: bool = False, db_id: str | None = None, supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service)):
    """
    학습 페이지 목록 조회
    - current=true : 현재 used DB 기준
    - db_id=<uuid> : 특정 DB 기준
    둘 다 지정시 db_id 결과
    """
    target_db_id = db_id
    if not target_db_id:
        if current:
            target_db_id = await get_used_notion_db_id(supabase, workspace_id)
        else:
            # 사용자가 필수 파라미터를 제공하지 않음 (사용자 실수)
            raise HTTPException(status_code=400, detail="db_id 또는 current=true 중 하나는 필수입니다.")

    if not target_db_id:
        # 활성화된 DB가 없음 (사용자 실수)
        raise HTTPException(status_code=404, detail="활성화된 학습 DB가 없습니다.")

    pages = await notion_service.list_all_pages(target_db_id)
    return {
        "db_id": target_db_id,
        "total": len(pages),
        "pages": pages
    }

@router.post("/pages/create")
async def create_pages(req: LearningPagesRequest, workspace_id: str = Depends(get_user_workspace_with_fallback), supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service), redis = Depends(get_redis)):
    notion_db_id = req.notion_db_id
    
    # WorkspaceCacheService를 사용해서 DB 목록 조회
    learning_data = await workspace_cache_service.get_workspace_learning_data(workspace_id, supabase, redis)
    databases = learning_data.get("databases", [])
    valid_db_ids = [db.get("db_id") for db in databases]
    
    if notion_db_id not in valid_db_ids:
        # 유효하지 않은 DB ID (사용자 실수)
        raise HTTPException(status_code=400, detail="학습 페이지 생성 실패: 유효한 DB가 아닙니다.")
    
    results = []

    for i, plan in enumerate(req.plans):
        try:
            # 멱등성 키 생성 (요청별 고유)
            import time
            import hashlib
            request_timestamp = int(time.time() * 1000)  # 밀리초 단위
            content_for_hash = f"{notion_db_id}_{plan.title}_{plan.date.isoformat()}_{i}_{request_timestamp}"
            idempotency_key = hashlib.md5(content_for_hash.encode()).hexdigest()[:12]
            
            api_logger.info(f"페이지 생성 시작 - 순번: {i+1}/{len(req.plans)}, 멱등성 키: {idempotency_key}")
            
            # 새로운 학습 행 생성
            page_id, ai_block_id = await notion_service.create_learning_page(notion_db_id, plan, idempotency_key)
            
            # 생성된 학습 행에 대한 메타 저장
            saved = await insert_learning_page(
                date=plan.date.isoformat(),
                title=plan.title,
                page_id=page_id,
                ai_block_id=ai_block_id,
                learning_db_id=notion_db_id,
                supabase=supabase
            )

            results.append({
                "page_id": page_id, 
                "ai_block_id": ai_block_id, 
                "saved": saved,
                "idempotency_key": idempotency_key
            })
            api_logger.info(f"페이지 생성 성공 - 순번: {i+1}, 페이지 ID: {page_id}")
        except Exception as e:
            # 개별 페이지 생성 실패는 비즈니스 로직상 results에 포함 (전체 실패 아님)
            api_logger.error(f"학습 페이지 생성 실패 (순번: {i+1}): {str(e)}")
            results.append({
                "error": str(e), 
                "plan": plan.model_dump(),
                "index": i
            })

    # 새 페이지가 생성되었으므로 워크스페이스 캐시 무효화
    if workspace_id and any(result.get("saved") for result in results):
        await workspace_cache_service.invalidate_workspace_cache(workspace_id, redis)
        api_logger.info(f"새 페이지 생성으로 워크스페이스 캐시 무효화: {workspace_id}")

    return {
        "status": "completed",
        "total": len(req.plans),
        "results": results
    }

@router.patch("/pages/{page_id}")
async def patch_page(page_id: str, req: PageUpdateRequest, notion_service: NotionService = Depends(get_notion_service)):
    payload = jsonable_encoder(req, by_alias=True, exclude_none=True)
    props = payload.get("props")
    content = payload.get("content")
    summary = payload.get("summary").get("summary") if payload.get("summary") else None
        
    if props is not None:
        props = serialize_page_props(props)
    
    await notion_service.update_learning_page_comprehensive(
        page_id,
        props=props if props else None,
        goal_intro=content.get("goal_intro") if content else None,
        goals=content.get("goals") if content else None,
        summary=summary
    )
    return {"status":"success", "page_id": page_id}

@router.get("/pages/{page_id}/content")
async def get_content(page_id: str, notion_service: NotionService = Depends(get_notion_service)):
    """페이지 전체 내용을 마크다운 문자열로 반환"""
    # 서비스에서 마크다운 변환까지 완료된 내용 받기
    content = await notion_service.get_page_content_as_markdown(page_id)
    
    return {
        "status": "success", 
        "data": content,
        "message": "페이지 내용 조회 성공"
    }

@router.delete("/pages/{page_id}")
async def delete_page(page_id: str, workspace_id: str = Depends(get_user_workspace_with_fallback), supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service), redis = Depends(get_redis)):
    await notion_service.delete_page(page_id)
    await delete_learning_page(page_id, supabase)
    
    # 페이지가 삭제되었으므로 워크스페이스 캐시 무효화
    cache_key = f"workspace:{workspace_id}:learning_data"
    await redis_service.delete_key(cache_key, redis)
    api_logger.info(f"페이지 삭제로 워크스페이스 캐시 무효화: {workspace_id}")
    
    return {"status": "deleted", "page_id": page_id}
    
@router.get("/pages/{page_id}/commits")
async def get_page_commits(page_id: str, workspace_id: str = Depends(get_user_workspace_with_fallback), redis: redis.Redis = Depends(get_redis), supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service)):
    """페이지의 ai_block에 있는 커밋 분석 토글 리스트 조회"""
    # 2. 페이지 아이디를 받아서, 해당 페이지의 ai_block_id 조회
    ai_block_id = await get_ai_block_id_by_page_id(page_id, workspace_id, supabase)
    if not ai_block_id:
        raise HTTPException(status_code=404, detail="AI 블록 ID를 찾을 수 없습니다.")
    
    # 3. ai_block_id를 받아서, 해당 페이지의 커밋 토글 리스트 조회
    summary = await notion_service.get_page_summary(ai_block_id)
    return {
        "status": "success",
        "data": summary,
        "message": "커밋 리스트 조회 성공"
    }

@router.get("/pages/{page_id}/commits/{commit_sha}")
async def get_commit_details(page_id: str, commit_sha: str, workspace_id: str = Depends(get_user_workspace_with_fallback), redis: redis.Redis = Depends(get_redis), supabase: AsyncClient = Depends(get_supabase), notion_service: NotionService = Depends(get_notion_service)):
    """특정 커밋의 상세 분석 내용 조회"""
    # 2. 페이지 아이디를 받아서, 해당 페이지의 ai_block_id 조회
    ai_block_id = await get_ai_block_id_by_page_id(page_id, workspace_id, supabase)
    if not ai_block_id:
        # AI 블록을 찾을 수 없음 (사용자 실수 - 잘못된 page_id)
        raise HTTPException(status_code=404, detail="AI 블록 ID를 찾을 수 없습니다.")
    
    # 3. ai_block_id와 commit_sha를 받아서, 해당 커밋의 상세 분석 내용 조회
    commit_details = await notion_service.get_commit_details(ai_block_id, commit_sha)
    return {
        "status": "success",
        "data": commit_details,
        "message": f"커밋 {commit_sha[:8]} 상세 조회 성공"
    }
