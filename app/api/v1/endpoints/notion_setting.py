from fastapi import APIRouter, Depends, HTTPException
from app.core.supabase_connect import get_supabase
from app.core.redis_connect import get_redis
from app.api.v1.dependencies.auth import require_user
from app.api.v1.dependencies.notion import get_notion_service
from app.services.redis_service import RedisService
from app.models.notion_workspace import UserWorkspace, WorkspaceStatusUpdate
from app.services.supa import get_workspaces, switch_active_workspace, get_default_workspace

router = APIRouter()
redis_service = RedisService()

@router.get("/workspaces")
async def list_workspaces(user_id: str = Depends(require_user), supabase = Depends(get_supabase)):
    """사용자의 Notion 워크스페이스 목록 조회"""
    workspaces = await get_workspaces(user_id, supabase)
    return workspaces

@router.post("/workspaces/active")
async def set_active_workspace(update: WorkspaceStatusUpdate, user_id: str = Depends(require_user), supabase = Depends(get_supabase), redis = Depends(get_redis)):
    """활성 워크스페이스 설정"""
    if update.user_id != user_id:
        raise HTTPException(status_code=403, detail="자신의 워크스페이스만 변경할 수 있습니다")
    
    # Supabase에서 워크스페이스 상태 업데이트
    result = await switch_active_workspace(update, supabase)
    
    await redis_service.set_user_workspace(user_id, update.workspace_id, redis)
    
    return {"success": True, "result": result}

@router.get("/top-pages")
async def get_top_level_pages(user_id: str = Depends(require_user), notion_service = Depends(get_notion_service), redis = Depends(get_redis), supabase = Depends(get_supabase)):
    """현재 활성 워크스페이스의 최상위 페이지 목록 조회"""
    try: 
        top_pages = redis_service.get_workspace_pages(workspace_id, redis)
        if top_pages:
            return {"pages": top_pages, "source": "cache"}
        
        
        # 현재 활성 워크스페이스 ID 조회
        workspace_id = await redis_service.get_user_workspace(user_id, redis)
        if not workspace_id:
            workspace_id = await get_default_workspace(user_id, supabase)
            if workspace_id:
                await redis_service.set_user_workspace(user_id, workspace_id, redis)
            else:
                raise HTTPException(status_code=404, detail="활성화된 워크스페이스가 없습니다")
            
        top_pages = await notion_service.get_workspace_top_pages(workspace_id)

        await redis_service.set_workspace_pages(workspace_id, top_pages, redis)
        
        return {"pages": top_pages, "source": "api"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    