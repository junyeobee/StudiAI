"""
사용자 인증 및 API 키 관리 엔드포인트
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict
from supabase._async.client import AsyncClient
from app.core.supabase_connect import get_supabase
from app.services.auth_service import (
    generate_api_key,
    get_masked_keys,
    revoke_api_key
)
from app.models.auth import ApiKeyResponse, ApiKeyList, MessageResponse

router = APIRouter()
public_router = APIRouter()

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