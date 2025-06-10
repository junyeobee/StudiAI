from fastapi import APIRouter, Depends, HTTPException
from app.core.supabase_connect import get_supabase
from app.core.redis_connect import get_redis
from app.api.v1.dependencies.auth import require_user
from app.api.v1.dependencies.notion import get_notion_service, get_notion_workspace
from app.services.redis_service import RedisService
from app.models.notion_workspace import UserWorkspace, WorkspaceStatusUpdate
from app.services.supa import get_workspaces, switch_active_workspace, get_default_workspace
from app.services.notion_service import NotionService
from app.services.supa_auth_service import get_user_workspaces

router = APIRouter()
redis_service = RedisService()

@router.get("/workspaces")
async def list_workspaces(
    user_id: str = Depends(require_user), 
    supabase = Depends(get_supabase),
    _: NotionService = Depends(get_notion_service)
):
    """사용자의 Notion 워크스페이스 목록 조회"""
    workspaces = await get_workspaces(user_id, supabase)
    if workspaces == []:
        # 워크스페이스가 없음 (사용자가 연동하지 않았거나 설정 안함)
        raise HTTPException(status_code=404, detail="워크스페이스를 찾을 수 없습니다.")
    
    return {"status": "success", "data": {"workspaces": workspaces}, "message": "노션 워크스페이스 목록 조회 성공", "source": "api"}

@router.post("/workspaces/active")
async def set_active_workspace(
    update: WorkspaceStatusUpdate, 
    user_id: str = Depends(require_user), 
    supabase = Depends(get_supabase), 
    redis = Depends(get_redis),
    _: NotionService = Depends(get_notion_service)
):
    """활성 워크스페이스 설정"""
    result = await switch_active_workspace(user_id, update, supabase)
    await redis_service.set_user_workspace(user_id, update.workspace_id, redis)
    return {"success": True, "result": result}

@router.get("/top-pages")
async def get_top_level_pages(
    user_id: str = Depends(require_user),
    workspace_id: str = Depends(get_notion_workspace),
    notion_service: NotionService = Depends(get_notion_service), 
    redis = Depends(get_redis)
):
    """현재 활성 워크스페이스의 최상위 페이지 목록 조회"""
    top_pages = await redis_service.get_workspace_pages(user_id, workspace_id, redis)
    if top_pages:
        return {"status": "success", "data": {"pages": top_pages}, "message": "워크스페이스 페이지 목록 조회 성공", "source": "cache"}
    
    print(top_pages)
    top_pages = await notion_service.get_workspace_top_pages()
    print(top_pages)
    await redis_service.set_workspace_pages(user_id, workspace_id, top_pages, redis)
    print("완료")
    return {"status": "success", "data": {"pages": top_pages}, "message": "워크스페이스 페이지 목록 조회 성공", "source": "api"}

@router.get("/set-top-page/{page_id}")
async def set_top_page(
    page_id: str,
    user_id: str = Depends(require_user),
    workspace_id: str = Depends(get_notion_workspace),
    redis = Depends(get_redis),
    _: NotionService = Depends(get_notion_service)
):
    """default 최상위 페이지 설정"""
    top_pages = await redis_service.set_default_page(user_id, workspace_id, page_id, redis)
    if top_pages:
        return {"status": "success", "data": {"pages": top_pages}, "message": "최상위 페이지 목록 설정 성공", "source": "cache"}

@router.get("/get-top-page")
async def get_top_page(
    user_id: str = Depends(require_user),
    workspace_id: str = Depends(get_notion_workspace),
    redis = Depends(get_redis),
    _: NotionService = Depends(get_notion_service)
):
    """default 최상위 페이지 조회"""
    top_page = await redis_service.get_default_page(user_id, workspace_id, redis)
    if top_page:
        return {"status": "success", "data": {"page": top_page}, "message": "default 최상위 페이지 조회 성공", "source": "cache"}

