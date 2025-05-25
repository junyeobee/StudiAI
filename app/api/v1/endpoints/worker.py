from fastapi import APIRouter, Depends
from app.utils.logger import api_logger
from app.core.redis_connect import get_redis
from worker.monitor import get_queue_stats, get_detailed_queue_info, get_worker_health
import redis

router = APIRouter()

@router.get("/health")
async def worker_health_check(redis_client: redis.Redis = Depends(get_redis)):
    """워커 상태 체크"""
    try:
        health_data = get_worker_health(redis_client)
        
        return {
            "status": "success",
            "data": health_data,
            "message": "워커 헬스 체크 완료"
        }
    except Exception as e:
        api_logger.error(f"워커 헬스 체크 실패: {str(e)}")
        return {
            "status": "error",
            "data": None,
            "message": f"워커 헬스 체크 실패: {str(e)}"
        }

@router.get("/queue/stats")
async def get_queue_statistics(redis_client: redis.Redis = Depends(get_redis)):
    """RQ 큐 통계 조회"""
    try:
        stats = get_queue_stats(redis_client)
        
        return {
            "status": "success",
            "data": stats,
            "message": "큐 통계 조회 성공"
        }
    except Exception as e:
        api_logger.error(f"큐 통계 조회 실패: {str(e)}")
        return {
            "status": "error",
            "data": None,
            "message": f"큐 통계 조회 실패: {str(e)}"
        }

@router.get("/queue/details")
async def get_queue_details(redis_client: redis.Redis = Depends(get_redis)):
    """RQ 큐 상세 정보 조회"""
    try:
        details = get_detailed_queue_info(redis_client)
        
        return {
            "status": "success",
            "data": details,
            "message": "큐 상세 정보 조회 성공"
        }
    except Exception as e:
        api_logger.error(f"큐 상세 정보 조회 실패: {str(e)}")
        return {
            "status": "error",
            "data": None,
            "message": f"큐 상세 정보 조회 실패: {str(e)}"
        }

@router.get("/monitor")
async def get_full_monitor_info(redis_client: redis.Redis = Depends(get_redis)):
    """전체 모니터링 정보 조회"""
    try:
        stats = get_queue_stats(redis_client)
        details = get_detailed_queue_info(redis_client)
        health = get_worker_health(redis_client)
        
        monitor_data = {
            "큐_통계": stats,
            "큐_상세정보": details,
            "헬스_체크": health
        }
        
        return {
            "status": "success",
            "data": monitor_data,
            "message": "전체 모니터링 정보 조회 성공"
        }
    except Exception as e:
        api_logger.error(f"모니터링 정보 조회 실패: {str(e)}")
        return {
            "status": "error",
            "data": None,
            "message": f"모니터링 정보 조회 실패: {str(e)}"
        }