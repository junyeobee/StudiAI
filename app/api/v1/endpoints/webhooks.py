"""
웹훅 관련 API 엔드포인트
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from app.core.supabase_connect import get_supabase
from supabase._async.client import AsyncClient
from app.services.supa import (
    get_failed_webhook_operations,
    get_webhook_operations,
    get_webhook_operation_detail
)

router = APIRouter()

@router.get("/operations/failed")
async def get_failed_operations(
    limit: int = 10,
    supabase: AsyncClient = Depends(get_supabase)
):
    """실패한 웹훅 작업 목록 조회 (GitHub Action용)"""
    operations = await get_failed_webhook_operations(supabase, limit)
    return {
        "status": "success",
        "data": operations,
        "message": f"실패한 웹훅 작업 {len(operations)}개 조회 완료"
    }

@router.get("/operations")
async def get_operations(
    status: Optional[str] = None,
    limit: int = 50,
    supabase: AsyncClient = Depends(get_supabase)
):
    """웹훅 작업 목록 조회"""
    operations = await get_webhook_operations(supabase, status, limit)
    return {
        "status": "success", 
        "data": operations,
        "message": f"웹훅 작업 {len(operations)}개 조회 완료"
    }

@router.get("/operations/{operation_id}")
async def get_operation_detail(
    operation_id: str,
    supabase: AsyncClient = Depends(get_supabase)
):
    """특정 웹훅 작업 상세 조회"""
    operation = await get_webhook_operation_detail(operation_id, supabase)
    
    if not operation:
        raise HTTPException(status_code=404, detail="웹훅 작업을 찾을 수 없습니다")
    
    return {
        "status": "success",
        "data": operation,
        "message": "웹훅 작업 상세 조회 완료"
    }