import redis
import asyncio
import os
import sys
from typing import Dict, List
from rq import Queue, SimpleWorker, Worker
from rq.timeouts import TimerDeathPenalty
from app.services.code_analysis_service import CodeAnalysisService
from app.core.config import settings
from app.utils.logger import api_logger
from supabase import create_client

# 버퍼링 비활성화
os.environ["PYTHONUNBUFFERED"] = "1"

# 새로운 모듈들 import
from worker.config import RQ_CONFIG
from worker.dead_letter_handle import handle_failed_job
from worker.optim_rq import RQOptimizer

# Windows용 워커 클래스
class WindowsSimpleWorker(SimpleWorker):
    """Windows에서 SIGALRM 신호 문제를 해결하는 워커"""
    death_penalty_class = TimerDeathPenalty

# Redis 설정
redis_host = settings.REDIS_HOST
redis_port = int(settings.REDIS_PORT)
redis_password = settings.REDIS_PASSWORD

# Redis 연결
redis_conn = redis.Redis(host=redis_host, port=redis_port, password=redis_password)

# RQ 큐 생성 (설정 적용)
task_queue = Queue(
    'code_analysis', 
    connection=redis_conn,
    default_timeout=RQ_CONFIG['worker']['timeout']
)

def analyze_code_task(files: List[Dict], owner: str, repo: str, commit_sha: str, user_id: str):
    """코드 분석 태스크 - RQ 워커에서 실행"""
    try:
        api_logger.info(f"RQ 워커에서 코드 분석 시작: {commit_sha[:8]}, 파일 수: {len(files)}")
        sys.stdout.flush()
        api_logger.info(f"사용자 ID: {user_id}, 저장소: {owner}/{repo}")
        sys.stdout.flush()

        asyncio.run(_analyze_code_async(files, owner, repo, commit_sha, user_id))
        sys.stdout.flush()

        api_logger.info(f"RQ 워커 코드 분석 완료: {commit_sha[:8]}")
        sys.stdout.flush()
        return {"status": "success", "commit_sha": commit_sha}
        
    except Exception as e:
        api_logger.error(f"RQ 워커 코드 분석 실패: {str(e)}")
        sys.stdout.flush()
        raise e

async def _analyze_code_async(files: List[Dict], owner: str, repo: str, commit_sha: str, user_id: str):
    """비동기 코드 분석 실행"""
    try:
        api_logger.info("Supabase 클라이언트 생성 중...")
        sys.stdout.flush()
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        
        api_logger.info("분석 서비스 초기화 중...")
        sys.stdout.flush()
        analysis_service = CodeAnalysisService(redis_conn, supabase)
        
        api_logger.info("코드 변경 분석 시작...")
        sys.stdout.flush()
        await analysis_service.analyze_code_changes(
            files=files,
            owner=owner,
            repo=repo,
            commit_sha=commit_sha,
            user_id=user_id
        )
        
        api_logger.info("큐 처리 시작...")
        sys.stdout.flush()
        await analysis_service.process_queue()
        
        api_logger.info("분석 완료")
        sys.stdout.flush()
        
    except Exception as e:
        api_logger.error(f"비동기 분석 실행 오류: {str(e)}")
        sys.stdout.flush()
        raise

def create_optimized_worker():
    """최적화된 워커 생성"""
    worker_config = RQ_CONFIG['worker']
    
    # 플랫폼별 워커 생성
    if os.name == 'nt':  # Windows
        worker = WindowsSimpleWorker(
            [task_queue], 
            connection=redis_conn,
            exception_handlers=[handle_failed_job]
        )
        api_logger.info("Windows용 최적화 워커 생성")
    else:  # Unix/Linux
        worker = Worker(
            [task_queue], 
            connection=redis_conn,
            exception_handlers=[handle_failed_job]
        )
        api_logger.info("Unix/Linux용 최적화 워커 생성")
    
    # 워커 설정 적용
    worker.default_result_ttl = worker_config['result_ttl']
    worker.default_worker_ttl = worker_config['default_worker_ttl']
    
    return worker

def start_worker():
    """RQ 워커 시작 - 최적화 및 모니터링 포함"""
    try:
        api_logger.info("=== RQ 최적화 워커 시작 ===")
        
        # 설정 정보 로깅
        api_logger.info(f"워커 설정: {RQ_CONFIG['worker']}")
        api_logger.info(f"실패 처리 설정: {RQ_CONFIG['failure']}")
        api_logger.info(f"스케일링 설정: {RQ_CONFIG['scaling']}")
        
        # 최적화된 워커 생성
        worker = create_optimized_worker()
        
        # 동적 스케일링 시작 (별도 스레드)
        if os.getenv('ENABLE_AUTO_SCALING', 'true').lower() == 'true':
            optimizer = RQOptimizer(redis_conn)
            optimizer.start_monitoring()
            api_logger.info("동적 스케일링 모니터링 시작")
        
        # 워커 시작
        api_logger.info("워커가 작업을 기다리고 있습니다...")
        worker.work(
            burst=False,  # 지속적 실행
            logging_level='INFO'
        )
        sys.stdout.flush()
            
    except KeyboardInterrupt:
        api_logger.info("워커 종료 신호 수신")
    except Exception as e:
        api_logger.error(f"RQ 워커 시작 실패: {str(e)}")
        raise
    finally:
        api_logger.info("RQ 워커 종료")

def start_worker_with_optimization():
    """최적화 기능이 포함된 워커 시작"""
    try:
        # 환경 체크
        api_logger.info("=== RQ 워커 환경 체크 ===")
        api_logger.info(f"플랫폼: {os.name}")
        api_logger.info(f"Redis 연결: {redis_host}:{redis_port}")
        
        # Redis 연결 테스트
        redis_conn.ping()
        api_logger.info("Redis 연결 성공")
        
        # 큐 상태 확인
        queue_size = len(task_queue)
        api_logger.info(f"현재 큐 크기: {queue_size}")
        
        # 워커 시작
        start_worker()
        
    except redis.ConnectionError as e:
        api_logger.error(f"Redis 연결 실패: {str(e)}")
        raise
    except Exception as e:
        api_logger.error(f"워커 시작 실패: {str(e)}")
        raise

if __name__ == '__main__':
    # 환경변수로 모드 선택
    mode = os.getenv('WORKER_MODE', 'optimized')
    
    if mode == 'optimized':
        start_worker_with_optimization()
    else:
        start_worker() 