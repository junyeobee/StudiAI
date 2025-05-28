from fastapi import Depends, HTTPException
from app.core.redis_connect import get_redis
from app.services.redis_service import RedisService
from app.core.supabase_connect import get_supabase
from supabase._async.client import AsyncClient
from app.services.notion_service import NotionService
from app.api.v1.dependencies.auth import require_user
from app.utils.logger import api_logger
import redis
from app.services.auth_service import get_integration_token
from app.services.supa import get_default_workspace,list_all_learning_databases

redis_service = RedisService()


async def get_notion_service(
    user_id: str = Depends(require_user), 
    supabase: AsyncClient = Depends(get_supabase),
    redis: redis.Redis = Depends(get_redis)
):
    # Redis 서비스 초기화
    try:
        # 먼저 Redis에서 토큰 조회 시도
        token = await redis_service.get_token(user_id, redis)
        
        # Redis에 토큰이 없으면 Supabase에서 조회 후 Redis에 저장
        if token is None:
            api_logger.info(f"Redis에 토큰 없음, Supabase에서 조회: {user_id}")
            token = await get_integration_token(user_id=user_id, provider="notion", supabase=supabase)
            
            # 조회한 토큰을 Redis에 저장 (1시간 만료)
            if token:
                await redis_service.set_token(user_id, token, redis, expire_seconds=3600)
        else:
            api_logger.info(f"Redis에서 토큰 조회 성공: {user_id}")
            
    except Exception as e:
        api_logger.error(f"Notion 토큰 조회 실패: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Notion 통합 정보가 없습니다."
        )
        
    return NotionService(token=token)

async def get_notion_workspace(user_id: str = Depends(require_user), supabase: AsyncClient = Depends(get_supabase), redis: redis.Redis = Depends(get_redis)) -> str:
    """기본 노션 워크스페이스 조회"""
    try:        
        # Redis에 저장된 워크스페이스 id 조회
        workspace_id = await redis_service.get_user_workspace(user_id, redis)
        if workspace_id:
            return workspace_id
        
        # 워크스페이스가 없으면 supabase에서 기본(active) 워크스페이스 조회
        workspace_id = await get_default_workspace(user_id, supabase)
        if workspace_id:
            # Redis에 워크스페이스 id 저장
            await redis_service.set_user_workspace(user_id, workspace_id, redis)
        
        return workspace_id
    except Exception as e:
        api_logger.error(f"노션 워크스페이스 조회 실패: {str(e)}")
        return "조회 실패"

async def get_notion_db_list(user_id: str = Depends(require_user), workspace_id: str = Depends(get_notion_workspace), supabase: AsyncClient = Depends(get_supabase), redis: redis.Redis = Depends(get_redis)) -> list:
    """노션 데이터베이스 목록 조회"""
    try:
        # Redis에 저장된 데이터베이스 목록 조회
        db_list = await redis_service.get_db_list(user_id, workspace_id, redis)
        if db_list:
            return db_list
        
        # Redis에 데이터베이스 목록이 없으면 supabase에서 조회
        db_list = await list_all_learning_databases(supabase, workspace_id)
        if db_list:
            # Redis에 데이터베이스 목록 저장
            await redis_service.set_db_list(user_id, workspace_id, db_list, redis)
        return db_list
    except Exception as e:
        api_logger.error(f"노션 데이터베이스 목록 조회 실패: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))