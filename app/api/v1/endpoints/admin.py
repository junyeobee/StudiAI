"""
관리자용 엔드포인트
에러 통계 및 시스템 모니터링 기능
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from supabase._async.client import AsyncClient
from app.core.supabase_connect import get_supabase
from app.api.v1.dependencies.auth import require_user
from app.services.error_log_service import get_error_statistics
from app.utils.logger import api_logger
from app.core.exceptions import (
    NotionAPIError, DatabaseError, WebhookError, ValidationError,
    LearningError, RedisError, GithubAPIError
)
from typing import Optional
import os

router = APIRouter()

@router.get("/error-statistics")
async def get_error_stats(
    version_tag: Optional[str] = Query(None, description="특정 버전의 통계만 조회 (선택)"),
    limit: int = Query(100, ge=1, le=1000, description="최대 조회 건수"),
    user_id: str = Depends(require_user),
    supabase: AsyncClient = Depends(get_supabase)
):
    """
    에러 통계 조회 (관리자용)
    
    Args:
        version_tag: 특정 버전 필터 (선택)
        limit: 조회할 최대 건수
        user_id: 인증된 사용자 ID
        supabase: Supabase 클라이언트
    
    Returns:
        에러 통계 정보
    """
    try:
        api_logger.info(f"에러 통계 조회 요청: user_id={user_id}, version_tag={version_tag}")
        
        # TODO: 실제 운영에서는 관리자 권한 체크 로직 추가
        # if not await is_admin_user(user_id, supabase):
        #     raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        
        stats = await get_error_statistics(
            supabase=supabase, 
            version_tag=version_tag, 
            limit=limit
        )
        
        return {
            "status": "success",
            "data": stats,
            "message": "에러 통계 조회 완료"
        }
        
    except Exception as e:
        api_logger.error(f"에러 통계 조회 실패: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail="에러 통계 조회 중 오류가 발생했습니다."
        )

@router.get("/health/error-logging")
async def check_error_logging_health(
    user_id: str = Depends(require_user),
    supabase: AsyncClient = Depends(get_supabase)
):
    """
    에러 로깅 시스템 건강성 체크
    
    Returns:
        에러 로깅 시스템 상태 정보
    """
    try:
        # 간단한 테스트 쿼리로 Supabase 연결 상태 확인
        result = await supabase.table("error_logs").select("id").limit(1).execute()
        
        return {
            "status": "success",
            "data": {
                "error_logging_status": "healthy",
                "supabase_connection": "connected",
                "last_check": api_logger.handlers[0].baseFilename if api_logger.handlers else "N/A"
            },
            "message": "에러 로깅 시스템 정상 동작"
        }
        
    except Exception as e:
        api_logger.error(f"에러 로깅 헬스체크 실패: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "data": {
                "error_logging_status": "unhealthy",
                "supabase_connection": "failed",
                "error_detail": str(e)
            },
            "message": "에러 로깅 시스템 문제 감지"
        }

# ============================================================================
# 개발/테스트용 엔드포인트들 (운영 환경에서는 제거 권장)
# ============================================================================

@router.post("/test/trigger-error/{error_type}")
async def trigger_test_error(
    error_type: str,
    user_id: str = Depends(require_user)
):
    """
    테스트용 예외 발생 엔드포인트
    
    Args:
        error_type: 발생시킬 예외 유형 (notion_api, database, webhook, validation, learning, redis, github_api, generic)
        user_id: 인증된 사용자 ID
    
    Note:
        개발 및 테스트 목적으로만 사용하며, 운영 환경에서는 제거해야 합니다.
    """
    # 개발 환경에서만 동작하도록 제한
    if os.getenv("ENVIRONMENT", "development") != "development":
        raise HTTPException(
            status_code=404, 
            detail="해당 엔드포인트는 개발 환경에서만 사용 가능합니다."
        )
    
    api_logger.info(f"테스트 예외 발생 요청: user_id={user_id}, error_type={error_type}")
    
    # 예외 유형별로 의도적으로 예외 발생
    if error_type == "notion_api":
        raise NotionAPIError("테스트용 Notion API 오류입니다.")
    elif error_type == "database":
        raise DatabaseError("테스트용 데이터베이스 오류입니다.")
    elif error_type == "webhook":
        raise WebhookError("테스트용 웹훅 오류입니다.")
    elif error_type == "validation":
        raise ValidationError("테스트용 검증 오류입니다.")
    elif error_type == "learning":
        raise LearningError("테스트용 학습 오류입니다.")
    elif error_type == "redis":
        raise RedisError("테스트용 Redis 오류입니다.")
    elif error_type == "github_api":
        raise GithubAPIError("테스트용 GitHub API 오류입니다.")
    elif error_type == "generic":
        raise Exception("테스트용 일반 예외입니다.")
    else:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 에러 유형: {error_type}. 사용 가능한 유형: notion_api, database, webhook, validation, learning, redis, github_api, generic"
        )

@router.get("/test/version-info")
async def get_version_info(user_id: str = Depends(require_user)):
    """
    현재 버전 정보 조회 (개발용)
    
    Returns:
        현재 설정된 APP_VERSION 환경 변수 값
    """
    if os.getenv("ENVIRONMENT", "development") != "development":
        raise HTTPException(
            status_code=404, 
            detail="해당 엔드포인트는 개발 환경에서만 사용 가능합니다."
        )
    
    return {
        "status": "success",
        "data": {
            "app_version": os.getenv("APP_VERSION", "unknown"),
            "environment": os.getenv("ENVIRONMENT", "development"),
            "user_id": user_id
        },
        "message": "버전 정보 조회 완료"
    } 