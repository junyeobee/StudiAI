from fastapi import APIRouter, Response, HTTPException
from app.services.code_analysis_service import CodeAnalysisService
from app.core.config import settings
from app.utils.logger import api_logger
from redis import Redis
import asyncio
import traceback
from typing import Dict, Any

router = APIRouter()

# ✅ Step 12: 헬스체크 엔드포인트 (24/7 운영 모니터링)

@router.get("/")
async def basic_health_check():
    """기본 헬스체크 (Docker 및 로드밸런서용)"""
    return {"status": "ok", "service": "notion-learning-api"}

@router.get("/healthz")
async def health_check():
    """기본 헬스체크 (Kubernetes Liveness Probe용)"""
    try:
        # Redis 연결 확인
        redis_client = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=False
        )
        redis_client.ping()
        
        return {"status": "ok", "timestamp": asyncio.get_event_loop().time()}
    except Exception as e:
        api_logger.error(f"헬스체크 실패: {e}")
        return Response(status_code=500, content=f"error: {e}")

@router.get("/health/ready")  
async def readiness_check():
    """준비 상태 확인 (Kubernetes Readiness Probe용)"""
    try:
        # Redis 연결 확인
        redis_client = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=False
        )
        redis_client.ping()
        
        # 공유 ThreadPoolExecutor 상태 확인
        executor_status = "ready" if CodeAnalysisService._shared_executor else "not_initialized"
        
        return {
            "status": "ready",
            "redis": "connected",
            "shared_executor": executor_status,
            "timestamp": asyncio.get_event_loop().time()
        }
    except Exception as e:
        api_logger.error(f"준비상태 확인 실패: {e}")
        return Response(status_code=503, content=f"not ready: {e}")

@router.get("/health/detailed")
async def detailed_health_check() -> Dict[str, Any]:
    """상세 헬스체크 (운영 모니터링용)"""
    health_status = {
        "status": "healthy",
        "timestamp": asyncio.get_event_loop().time(),
        "components": {}
    }
    
    try:
        # Redis 상태 확인
        redis_client = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=False
        )
        
        redis_info = redis_client.info("memory")
        health_status["components"]["redis"] = {
            "status": "healthy",
            "used_memory_mb": round(int(redis_info.get("used_memory", 0)) / 1024 / 1024, 2),
            "connected_clients": redis_info.get("connected_clients", 0)
        }
        
        # 공유 ThreadPoolExecutor 상태
        if CodeAnalysisService._shared_executor:
            executor = CodeAnalysisService._shared_executor
            health_status["components"]["thread_pool"] = {
                "status": "active",
                "max_workers": executor._max_workers,
                "threads_count": len(executor._threads) if hasattr(executor, '_threads') else "unknown"
            }
        else:
            health_status["components"]["thread_pool"] = {
                "status": "not_initialized"
            }
        
        # 시스템 정보
        import psutil
        health_status["components"]["system"] = {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent
        }
        
        return health_status
        
    except Exception as e:
        api_logger.error(f"상세 헬스체크 실패: {e}")
        api_logger.error(traceback.format_exc())
        health_status["status"] = "unhealthy"
        health_status["error"] = str(e)
        return health_status

@router.get("/health/metrics")
async def prometheus_metrics():
    """Prometheus 메트릭 (모니터링 시스템용)"""
    try:
        redis_client = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=False
        )
        
        redis_info = redis_client.info("memory")
        
        metrics = []
        metrics.append(f"rq_worker_redis_memory_bytes {redis_info.get('used_memory', 0)}")
        metrics.append(f"rq_worker_redis_connected_clients {redis_info.get('connected_clients', 0)}")
        
        # ThreadPoolExecutor 메트릭
        if CodeAnalysisService._shared_executor:
            executor = CodeAnalysisService._shared_executor
            metrics.append(f"rq_worker_thread_pool_max_workers {executor._max_workers}")
            thread_count = len(executor._threads) if hasattr(executor, '_threads') else 0
            metrics.append(f"rq_worker_thread_pool_active_threads {thread_count}")
            metrics.append("rq_worker_thread_pool_status 1")
        else:
            metrics.append("rq_worker_thread_pool_status 0")
        
        # 시스템 메트릭
        import psutil
        metrics.append(f"rq_worker_cpu_percent {psutil.cpu_percent()}")
        metrics.append(f"rq_worker_memory_percent {psutil.virtual_memory().percent}")
        
        return Response(content="\n".join(metrics), media_type="text/plain")
        
    except Exception as e:
        api_logger.error(f"메트릭 생성 실패: {e}")
        return Response(status_code=500, content=f"# ERROR: {e}")

@router.post("/health/cleanup")
async def cleanup_resources():
    """리소스 정리 (Blue/Green 배포 시 사용)"""
    try:
        # ThreadPoolExecutor 정리
        await CodeAnalysisService.cleanup_executor()
        
        return {
            "status": "cleaned",
            "message": "ThreadPoolExecutor가 정상 종료되었습니다",
            "timestamp": asyncio.get_event_loop().time()
        }
    except Exception as e:
        api_logger.error(f"리소스 정리 실패: {e}")
        api_logger.error(traceback.format_exc())
        return Response(status_code=500, content=f"cleanup failed: {e}") 