"""
사용자 인증 및 API 키 관리 엔드포인트
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Optional
from supabase._async.client import AsyncClient
from app.core.supabase_connect import get_supabase
from app.services.auth_service import (
    generate_api_key,
    get_masked_keys,
    revoke_api_key
)
from app.core.redis_connect import get_redis
from app.models.auth import ApiKeyResponse, ApiKeyList, MessageResponse, UserIntegrationRequest, UserIntegrationResponse
from app.services.auth_service import encrypt_token, get_integration_token, get_integration_by_id
from app.api.v1.dependencies.auth import require_user
from fastapi import Query
from app.services.auth_service import process_notion_oauth, parse_oauth_state, process_github_oauth
from app.core.config import settings
import urllib.parse
from app.services.redis_service import RedisService

router = APIRouter()
public_router = APIRouter()
redis_service = RedisService()

# 임시 저장소 (실제로는 Redis 사용 예정)
temp_state_store = {
    "user_id": "ㅁㄴㅇㄹ",
    "uuid": "fixed-state-uuid-12345"
}

@public_router.post("/keys", response_model=ApiKeyResponse)
async def create_api_key(
    user_id: str,
    supabase: AsyncClient = Depends(get_supabase)
):
    """
    새로운 API 키 발급
    
    user_id: 사용자 식별자
    """
    key = await generate_api_key(user_id, supabase)
    if not key:
        raise HTTPException(
            status_code=500, 
            detail="API 키 생성 실패"
        )
    
    return ApiKeyResponse(key=key)


@router.get("/keys", response_model=ApiKeyList)
async def list_api_keys(
    user_id: str,
    supabase: AsyncClient = Depends(get_supabase)
):
    """
    사용자의 모든 API 키 목록 조회 (마스킹 처리됨)
    
    user_id: 사용자 식별자
    """
    keys = await get_masked_keys(user_id, supabase)
    return ApiKeyList(keys=keys)


@router.delete("/keys/{key_id}", response_model=MessageResponse)
async def delete_api_key(
    key_id: str,
    user_id: str,
    supabase: AsyncClient = Depends(get_supabase)
):
    """
    API 키 비활성화
    
    key_id: 삭제할 API 키 ID
    user_id: 사용자 식별자
    """
    success = await revoke_api_key(key_id, user_id, supabase)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="API 키 비활성화 실패"
        )
    
    return MessageResponse(
        message="API 키가 성공적으로 비활성화되었습니다",
        success=True
    ) 

@router.post("/integrations", response_model=UserIntegrationResponse)
async def create_integration(request: UserIntegrationRequest, user_id: str = Depends(require_user),supabase: AsyncClient = Depends(get_supabase)):
    """
    새로운 통합 생성
    """
    try:
        return await encrypt_token(user_id,request, supabase)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

@router.get("/integrations/{provider}")
async def get_integration(provider: str, user_id: str = Depends(require_user),supabase: AsyncClient = Depends(get_supabase)):
    """
    통합 정보 조회
    """
    try:
        return await get_integration_token(user_id, provider, supabase)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
    
@router.get("/oauth/{provider}")
async def initiate_oauth(provider: str, user_id: str = Depends(require_user), redis = Depends(get_redis)):
    """
    OAuth 인증 시작
    """
    try:
        # state_uuid 생성
        state_uuid = await redis_service.set_state_uuid(user_id, redis)
        print(state_uuid + "생성")
        # state 파라미터 생성 (검증용)
        state_param = f"user_id={user_id}|uuid={state_uuid}"
        
        # 리다이렉트 URL 생성
        match provider:
            case "notion":
                redirect_uri = f"{settings.API_BASE_URL}/auth_public/callback/notion"
                encoded_state_param = urllib.parse.quote(state_param)
                notion_auth_url = f"https://api.notion.com/v1/oauth/authorize?client_id={settings.NOTION_CLIENT_ID}&redirect_uri={redirect_uri}&response_type=code&state={encoded_state_param}"
                return {"auth_url": notion_auth_url}
            case "github":
                redirect_uri = f"{settings.API_BASE_URL}/auth_public/callback/github"
                encoded_redirect_uri = urllib.parse.quote(redirect_uri)
                encoded_state_param = urllib.parse.quote(state_param)
                
                # 명시적으로 repo 및 admin:repo_hook 권한 요청
                scope = "repo admin:repo_hook"
                encoded_scope = urllib.parse.quote(scope)
                
                # GitHub OAuth 인증 URL 구성
                github_auth_url = f"https://github.com/login/oauth/authorize?client_id={settings.GITHUB_CLIENT_ID}&redirect_uri={encoded_redirect_uri}&scope={encoded_scope}&state={encoded_state_param}"
                
                return {"auth_url": github_auth_url}
            case _:
                raise HTTPException(status_code=400, detail=f"지원하지 않는 제공자: {provider}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@public_router.get("/callback/{provider}")
async def token_callback_get(provider: str, code: str = Query(...), state: str = Query(None), supabase: AsyncClient = Depends(get_supabase), redis = Depends(get_redis)):
    """
    OAuth 콜백 처리: 코드 교환, state 검증, 토큰 저장, 워크스페이스 저장
    """
    try:
        # 1. state 파싱
        user_id, state_uuid = parse_oauth_state(state)
        print(user_id, state_uuid)
        if not user_id or not state_uuid:
            raise HTTPException(status_code=401, detail="인증 정보 없음")
        
        # 2. state 검증
        valid = await redis_service.validate_state_uuid(user_id, state_uuid, redis)
        if not valid:
            raise HTTPException(status_code=401, detail="인증 토큰 검증 실패 또는 만료됨")
        
        match provider:
            case "notion":
                result = await process_notion_oauth(user_id, code, supabase)
                return {
                    "message": "노션 토큰 설정 완료, AI AGENT로 돌아가주세요.",
                    **result
                }
            case "github":
                result = await process_github_oauth(user_id, code, supabase)
                return {
                    "message": "깃허브 토큰 설정 완료, AI AGENT로 돌아가주세요.",
                    **result
                }
            case _:
                raise HTTPException(status_code=400, detail=f"지원하지 않는 제공자: {provider}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))