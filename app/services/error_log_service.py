from datetime import datetime
from typing import Optional
from supabase._async.client import AsyncClient
from app.utils.logger import api_logger
from app.core.config import settings

async def save_error_to_db(
    supabase: AsyncClient,
    *,
    timestamp: str,
    endpoint: str,
    method: str,
    exception_type: str,
    detail: str,
    stack_trace: Optional[str] = None,
    user_id: Optional[str] = None,
    version_tag: Optional[str] = None
) -> bool:
    """
    에러 정보를 Supabase error_logs 테이블에 저장
    
    Args:
        supabase: Supabase 비동기 클라이언트
        timestamp: 에러 발생 시각 (ISO 형식)
        endpoint: 요청된 경로
        method: HTTP 메서드
        exception_type: 예외 클래스명
        detail: 예외 메시지
        stack_trace: 스택 트레이스 (선택)
        user_id: 사용자 ID (선택)
        version_tag: Git 태그/커밋 해시 (선택)
    
    Returns:
        저장 성공 여부
    """
    try:
        # 환경 변수에서 버전 태그 가져오기 (없으면 "unknown")
        if version_tag is None:
            version_tag = settings.APP_VERSION
        
        # 에러 로그 데이터 구성
        error_data = {
            "timestamp": timestamp,
            "version_tag": version_tag,
            "endpoint": endpoint,
            "method": method,
            "exception_type": exception_type,
            "detail": detail,
            "stack_trace": stack_trace,
            "user_id": user_id
        }
        
        # Supabase에 저장
        result = await supabase.table("error_logs").insert(error_data).execute()
        
        if result.data:
            api_logger.info(f"에러 로그 저장 성공: {exception_type} - {endpoint}")
            return True
        else:
            api_logger.error(f"에러 로그 저장 실패: 응답 데이터 없음")
            return False
            
    except Exception as e:
        # 에러 로깅 자체가 실패하면 콘솔에만 기록
        api_logger.error(f"에러 로그 저장 실패: {str(e)}", exc_info=True)
        return False


async def get_error_statistics(
    supabase: AsyncClient,
    version_tag: Optional[str] = None,
    limit: int = 100
) -> dict:
    """
    에러 통계 조회 (선택적 기능)
    
    Args:
        supabase: Supabase 비동기 클라이언트
        version_tag: 특정 버전의 통계만 조회 (선택)
        limit: 최대 조회 건수
    
    Returns:
        에러 통계 딕셔너리
    """
    try:
        query = supabase.table("error_logs").select("exception_type, endpoint, method, timestamp")
        
        if version_tag:
            query = query.eq("version_tag", version_tag)
            
        result = await query.order("timestamp", desc=True).limit(limit).execute()
        
        if result.data:
            # 간단한 통계 계산
            error_counts = {}
            endpoint_counts = {}
            
            for error in result.data:
                exc_type = error["exception_type"]
                endpoint = error["endpoint"]
                
                error_counts[exc_type] = error_counts.get(exc_type, 0) + 1
                endpoint_counts[endpoint] = endpoint_counts.get(endpoint, 0) + 1
            
            return {
                "에러 발생 건수": len(result.data),
                "에러 타입별 발생 건수": error_counts,
                "에러 발생 엔드포인트별 건수": endpoint_counts,
                "버전 태그": version_tag or "all"
            }
        else:
            return {
                "에러 발생 건수": 0,
                "에러 타입별 발생 건수": {},
                "에러 발생 엔드포인트별 건수": {},
                "버전 태그": version_tag or "all"
            }
            
    except Exception as e:
        api_logger.error(f"에러 통계 조회 실패: {str(e)}", exc_info=True)
        return {
            "에러 통계 조회 실패": f"{str(e)}",
            "버전 태그": version_tag or "all"
        } 