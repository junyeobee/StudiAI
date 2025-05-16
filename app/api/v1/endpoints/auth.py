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
from app.models.auth import ApiKeyResponse, ApiKeyList, MessageResponse
from app.models.auth import UserIntegrationRequest, UserIntegrationResponse
from app.services.auth_service import encrypt_token, get_integration_token, get_integration_by_id
from app.api.v1.dependencies.auth import require_user
from fastapi import Query
from app.services.notion_service import NotionService
from app.core.config import settings
from app.api.v1.dependencies.notion import get_notion_service
from app.services.notion_auth import NotionAuthService

router = APIRouter()
public_router = APIRouter()

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
async def initiate_oauth(provider: str, user_id: str = Depends(require_user)):
    """
    OAuth 인증 시작
    """
    try:
        # 고정된 state 값 사용 (실제로는 UUID 사용 예정)
        state_uuid = "fixed-state-uuid-12345"
        
        # state 파라미터 생성 (검증용)
        state_param = f"user_id={user_id}|uuid={state_uuid}"
        
        # 리다이렉트 URL 생성
        if provider == "notion":
            redirect_uri = "http://localhost:8000/auth_public/callback/notion"
            notion_auth_url = f"https://api.notion.com/v1/oauth/authorize?client_id={settings.NOTION_CLIENT_ID}&redirect_uri={redirect_uri}&response_type=code&state={state_param}"
            return {"auth_url": notion_auth_url}
        else:
            raise HTTPException(status_code=400, detail=f"지원하지 않는 제공자: {provider}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@public_router.get("/callback/{provider}")
async def token_callback_get(provider: str, code: str = Query(...), state: str = Query(None), supabase: AsyncClient = Depends(get_supabase)):
    """
    OAuth 콜백 처리: 코드 교환, 토큰 저장까지 한번에 처리
    """
    try:
        # state 파싱
        user_id = None
        state_uuid = None
        print(state)
        print(code)
        print(provider)
        if state:
            state_parts = state.split("|")
            for part in state_parts:
                match part:
                    case p if p.startswith("user_id="):
                        user_id = p.split("user_id=")[1]
                        print(user_id)
                    case p if p.startswith("uuid="):
                        state_uuid = p.split("uuid=")[1]
                        print(state_uuid)
        if not user_id or not state_uuid:
            raise HTTPException(status_code=401, detail="인증 정보 없음")
        
        # UUID 검증 (임시 저장소에서 확인)
        stored_uuid = temp_state_store.get("uuid")
        print(stored_uuid)
        if not stored_uuid or stored_uuid != state_uuid:
            raise HTTPException(status_code=401, detail="인증 토큰 검증 실패")
        
        integration_data = await get_integration_by_id(user_id, provider, supabase)
        
        # provider에 따라 토큰 교환
        match provider:
            case "notion":
                notion_auth_service = NotionAuthService()
                # 1. NotionService 인스턴스화하여 토큰 교환
                token_data = await notion_auth_service.exchange_code_for_token(code)
                workspace_id = token_data["workspace_id"]
                print(f'workspace_id: {workspace_id}')
                print(f'token_data: {token_data}')
                if integration_data:
                    token_request = UserIntegrationRequest(
                        id=integration_data["id"],
                        user_id=user_id,
                        provider=provider,
                        access_token=token_data["access_token"],
                        refresh_token=token_data.get("refresh_token"),
                        expires_in=token_data.get("expires_in"),
                        scopes=token_data.get("scope", "").split() if token_data.get("scope") else None
                    )
                    # 2. 토큰 요청 모델 생성
                else:
                    token_request = UserIntegrationRequest(
                        user_id=user_id,
                        provider=provider,
                        access_token=token_data["access_token"],
                        refresh_token=token_data.get("refresh_token"),
                        expires_in=token_data.get("expires_in"),
                        scopes=token_data.get("scope", "").split() if token_data.get("scope") else None
                    )

                # 3. 토큰 암호화 및 저장
                result = await encrypt_token(user_id, token_request, supabase)
                
                # 4. 성공 응답 반환
                return {"message": "노션 토큰 설정 완료, AI AGENT로 돌아가주세요.", "provider": provider, "integration_id": result["id"] if isinstance(result, dict) and "id" in result else None}
            case "github":
                return {"message": "깃허브 토큰 설정 완료, AI AGENT로 돌아가주세요.", "provider": provider, "integration_id": result["id"] if isinstance(result, dict) and "id" in result else None}
            case _:
                raise HTTPException(status_code=400, detail=f"지원하지 않는 제공자: {provider}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))