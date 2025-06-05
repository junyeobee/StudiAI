"""
전역 예외 핸들러 모듈
모든 커스텀 예외를 종류별로 분류하여 처리하고 Supabase에 저장
"""
import traceback
from datetime import datetime, timezone
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import JSONResponse
from supabase._async.client import AsyncClient
from app.core.config import settings

from app.core.exceptions import (
    NotionAPIError,
    DatabaseError,
    WebhookError,
    NotFoundError,
    ValidationError,
    LearningError,
    RedisError,
    GithubAPIError,
    WebhookOperationError
)
from app.services.error_log_service import save_error_to_db
from app.utils.logger import api_logger
from worker.monitor import QueueError


async def _create_error_log_data(request: Request, exc: Exception) -> dict:
    """에러 로그 데이터 생성 헬퍼 함수"""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "endpoint": request.url.path,
        "method": request.method,
        "exception_type": exc.__class__.__name__,
        "detail": str(exc),
        "stack_trace": traceback.format_exc(),
        "user_id": getattr(request.state, 'user_id', None),
        "version_tag": settings.APP_VERSION
    }


async def _save_error_and_respond(
    request: Request, 
    exc: Exception, 
    status_code: int, 
    user_message: str
) -> JSONResponse:
    """에러 저장 및 응답 생성 헬퍼 함수"""
    try:
        # 에러 로그 데이터 생성
        error_data = await _create_error_log_data(request, exc)
        
        # 콘솔 로깅
        api_logger.error(
            f"[{exc.__class__.__name__}] {request.method} {request.url.path} - {str(exc)}", 
            exc_info=True
        )
        
        # Supabase 클라이언트를 앱 상태에서 가져와서 저장
        if hasattr(request.app.state, 'supabase'):
            supabase = request.app.state.supabase
            await save_error_to_db(supabase, **error_data)
        else:
            api_logger.warning("Supabase 클라이언트를 찾을 수 없어 에러 로그 저장을 건너뜁니다.")
        
    except Exception as save_error:
        # 에러 저장 자체가 실패해도 응답은 계속 진행
        api_logger.error(f"에러 저장 실패: {str(save_error)}", exc_info=True)
    
    # 클라이언트 응답
    return JSONResponse(
        status_code=status_code,
        content={"detail": user_message}
    )


# ============================================================================
# FastAPI 기본 예외 핸들러
# ============================================================================

async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    """HTTPException 처리 (FastAPI 기본 예외)"""
    try:
        # 에러 로그 데이터 생성 및 저장
        error_data = await _create_error_log_data(request, exc)
        
        # 콘솔 로깅 (HTTPException은 일반적이므로 INFO 레벨로)
        if exc.status_code >= 500:
            # 5xx 에러는 ERROR 레벨로 로깅
            api_logger.error(
                f"[HTTPException] {request.method} {request.url.path} - {exc.status_code}: {exc.detail}", 
                exc_info=True
            )
        else:
            # 4xx 에러는 WARNING 레벨로 로깅
            api_logger.warning(
                f"[HTTPException] {request.method} {request.url.path} - {exc.status_code}: {exc.detail}"
            )
        
        if hasattr(request.app.state, 'supabase'):
            supabase = request.app.state.supabase
            await save_error_to_db(supabase, **error_data)
        
    except Exception as save_error:
        api_logger.error(f"HTTPException 로그 저장 실패: {str(save_error)}", exc_info=True)
    
    # 원본 HTTPException의 응답 그대로 반환
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


# ============================================================================
# 커스텀 예외별 핸들러들
# ============================================================================

async def handle_notion_api_error(request: Request, exc: NotionAPIError) -> JSONResponse:
    """Notion API 오류 처리"""
    return await _save_error_and_respond(
        request=request,
        exc=exc,
        status_code=status.HTTP_502_BAD_GATEWAY,
        user_message="Notion API 통신 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
    )


async def handle_database_error(request: Request, exc: DatabaseError) -> JSONResponse:
    """데이터베이스 오류 처리"""
    return await _save_error_and_respond(
        request=request,
        exc=exc,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        user_message="데이터베이스 처리 중 오류가 발생했습니다. 운영팀에 문의하세요."
    )


async def handle_webhook_error(request: Request, exc: WebhookError) -> JSONResponse:
    """웹훅 오류 처리"""
    return await _save_error_and_respond(
        request=request,
        exc=exc,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        user_message="웹훅 처리 중 오류가 발생했습니다. 운영팀에 문의하세요."
    )


async def handle_not_found_error(request: Request, exc: NotFoundError) -> JSONResponse:
    """리소스 없음 오류 처리"""
    return await _save_error_and_respond(
        request=request,
        exc=exc,
        status_code=status.HTTP_404_NOT_FOUND,
        user_message="요청한 리소스를 찾을 수 없습니다."
    )


async def handle_validation_error(request: Request, exc: ValidationError) -> JSONResponse:
    """검증 오류 처리"""
    return await _save_error_and_respond(
        request=request,
        exc=exc,
        status_code=status.HTTP_400_BAD_REQUEST,
        user_message="입력값 검증에 실패했습니다. Tool Helper를 호출하여 형식을 확인하세요."
    )


async def handle_learning_error(request: Request, exc: LearningError) -> JSONResponse:
    """학습 관련 오류 처리"""
    return await _save_error_and_respond(
        request=request,
        exc=exc,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        user_message="학습 처리 중 오류가 발생했습니다. 운영팀에 문의하세요."
    )


async def handle_redis_error(request: Request, exc: RedisError) -> JSONResponse:
    """Redis 오류 처리"""
    return await _save_error_and_respond(
        request=request,
        exc=exc,
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        user_message="캐시 서비스에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해주세요."
    )


async def handle_github_api_error(request: Request, exc: GithubAPIError) -> JSONResponse:
    """GitHub API 오류 처리"""
    return await _save_error_and_respond(
        request=request,
        exc=exc,
        status_code=status.HTTP_502_BAD_GATEWAY,
        user_message="GitHub API 통신 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
    )


async def handle_webhook_operation_error(request: Request, exc: WebhookOperationError) -> JSONResponse:
    """웹훅 작업 오류 처리"""
    return await _save_error_and_respond(
        request=request,
        exc=exc,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        user_message="웹훅 작업 처리 중 오류가 발생했습니다. 운영팀에 문의하세요."
    )


async def handle_generic_error(request: Request, exc: Exception) -> JSONResponse:
    """기타 모든 예외 처리 (최종 핸들러)"""
    return await _save_error_and_respond(
        request=request,
        exc=exc,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        user_message="서버 내부 오류가 발생했습니다. 문제가 지속되면 운영팀에 문의하세요."
    )


async def queue_error_handler(request: Request, exc: QueueError) -> JSONResponse:
    """QueueError (RQ 큐 관련 오류) 전역 핸들러"""
    api_logger.error(f"Queue error: {str(exc)}")
    
    await save_error_to_db(
        supabase=request.app.state.supabase,
        timestamp=datetime.now(timezone.utc).isoformat(),
        endpoint=request.url.path,
        method=request.method,
        exception_type="QueueError",
        detail=str(exc),
        stack_trace=traceback.format_exc()
    )
    
    return JSONResponse(
        status_code=503,  # Service Unavailable
        content={
            "status": "error",
            "message": "큐 서비스 오류가 발생했습니다",
            "detail": str(exc)
        }
    )


# ============================================================================
# 핸들러 등록 함수
# ============================================================================

def register_exception_handlers(app: FastAPI) -> None:
    """
    FastAPI 앱에 모든 예외 핸들러를 등록하는 함수
    
    Args:
        app: FastAPI 애플리케이션 인스턴스
    """
    # FastAPI 기본 예외 핸들러 (가장 먼저 등록)
    app.add_exception_handler(HTTPException, handle_http_exception)
    
    # 커스텀 예외들을 우선적으로 등록 (구체적인 예외부터)
    app.add_exception_handler(NotionAPIError, handle_notion_api_error)
    app.add_exception_handler(DatabaseError, handle_database_error)
    app.add_exception_handler(WebhookError, handle_webhook_error)
    app.add_exception_handler(NotFoundError, handle_not_found_error)
    app.add_exception_handler(ValidationError, handle_validation_error)
    app.add_exception_handler(LearningError, handle_learning_error)
    app.add_exception_handler(RedisError, handle_redis_error)
    app.add_exception_handler(GithubAPIError, handle_github_api_error)
    app.add_exception_handler(WebhookOperationError, handle_webhook_operation_error)
    app.add_exception_handler(QueueError, queue_error_handler)
    
    # 마지막에 일반 Exception 핸들러 등록 (최종 catch-all)
    app.add_exception_handler(Exception, handle_generic_error)
    
    api_logger.info("모든 예외 핸들러가 성공적으로 등록되었습니다.") 