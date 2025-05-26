import asyncio
import json
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from rq import Queue
from rq.job import Job
from rq import Retry
from worker.config import RQ_CONFIG
from app.utils.logger import api_logger
import redis

class DeadLetterHandlerWin:
    """Windows 환경 전용 실패한 작업 처리 클래스"""
    
    def __init__(self, redis_conn: redis.Redis):
        self.redis_conn = redis_conn
        self.config = RQ_CONFIG['failure']
        self.retry_queue = Queue('retry_queue', connection=redis_conn)
        self.dead_letter_queue = Queue('dead_letter_queue', connection=redis_conn)
        
        # Windows 스레드 풀 (asyncio 문제 해결용)
        self.thread_pool = ThreadPoolExecutor(
            max_workers=4, 
            thread_name_prefix="RQFailureHandler"
        )
        self.lock = threading.Lock()  # 스레드 안전성
    
    def handle_failed_job(self, job: Job, exc_type, exc_value, traceback):
        """실패한 작업 처리 메인 로직 - Windows 버전"""
        try:
            failed_job_data = self._extract_job_data(job, exc_value)
            
            api_logger.error(f"작업 실패: {failed_job_data['job_id']} - {failed_job_data['error']}")
            
            # 재시도 가능한지 확인
            if self._should_retry(failed_job_data):
                self._schedule_retry(job, failed_job_data)
            else:
                self._move_to_dead_letter(job, failed_job_data)
                
        except Exception as e:
            api_logger.error(f"실패 처리 중 오류: {str(e)}")
    
    def _extract_job_data(self, job: Job, exc_value) -> Dict[str, Any]:
        """작업 데이터 추출 - Windows 안전 버전"""
        return {
            'job_id': job.id,
            'function_name': job.func_name,
            'args': job.args if hasattr(job, 'args') else [],
            'kwargs': job.kwargs if hasattr(job, 'kwargs') else {},
            'error': str(exc_value),
            'retry_count': job.meta.get('retry_count', 0),
            'failed_at': datetime.now().isoformat(),
            'queue_name': job.origin if hasattr(job, 'origin') else 'unknown',
            'platform': 'Windows'
        }
    
    def _should_retry(self, failed_job_data: Dict[str, Any]) -> bool:
        """재시도 가능 여부 확인 - Windows 특화 조건"""
        retry_count = failed_job_data['retry_count']
        max_retries = self.config['max_retries']
        
        # Windows 특화 에러 처리
        error_msg = failed_job_data['error'].lower()
        
        # Windows에서 재시도하면 안 되는 에러들
        non_retryable_errors = [
            'access is denied',  # 접근 권한 오류
            'file not found',    # 파일 없음
            'permission denied', # 권한 오류
            'invalid handle',    # 핸들 오류
            'sharing violation'  # 파일 공유 오류
        ]
        
        if any(error in error_msg for error in non_retryable_errors):
            api_logger.warning(f"Windows 시스템 오류로 재시도 건너뜀: {failed_job_data['error']}")
            return False
        
        # DB 실패 횟수도 확인
        db_failure_count = self._get_db_failure_count(failed_job_data['job_id'])
        max_db_failures = self.config['max_db_failures']
        
        return (retry_count < max_retries and 
                db_failure_count < max_db_failures)
    
    def _schedule_retry(self, job: Job, failed_job_data: Dict[str, Any]):
        """재시도 스케줄링 - Windows ThreadPoolExecutor 사용"""
        retry_count = failed_job_data['retry_count'] + 1
        
        # Windows에서 더 긴 재시도 간격 (시스템 리소스 고려)
        base_delay = self.config['retry_delay']
        retry_delay = min(base_delay * (2 ** (retry_count - 1)), 300)  # 최대 5분
        
        # 메타데이터 업데이트 (스레드 안전)
        with self.lock:
            job.meta['retry_count'] = retry_count
            job.meta['last_failure'] = failed_job_data['failed_at']
            job.meta['last_error'] = failed_job_data['error']
            job.meta['platform'] = 'Windows'
            job.save_meta()
        
        try:
            # RQ Retry 객체 사용 (공식 권장 방식)
            retry_obj = Retry(max=1, interval=retry_delay)
            
            # 재시도 큐에 등록
            self.retry_queue.enqueue_in(
                timedelta(seconds=retry_delay),
                job.func,
                *job.args,
                **job.kwargs,
                job_id=f"{job.id}_retry_{retry_count}",
                retry=retry_obj,
                meta=job.meta
            )
            
            api_logger.info(f"작업 재시도 예약: {job.id} (시도 {retry_count}/{self.config['max_retries']}, {retry_delay}초 후)")
            
            # 스레드 풀로 DB 저장 (Windows asyncio 이슈 회피)
            self.thread_pool.submit(
                self._save_retry_log_sync, 
                failed_job_data.copy(), 
                retry_count
            )
            
        except Exception as e:
            api_logger.error(f"재시도 스케줄링 실패: {str(e)}")
    
    def _move_to_dead_letter(self, job: Job, failed_job_data: Dict[str, Any]):
        """데드 레터 큐로 이동 - Windows 버전"""
        try:
            # 최종 실패 메타데이터 추가
            with self.lock:
                job.meta['final_failure'] = True
                job.meta['total_retries'] = failed_job_data['retry_count']
                job.meta['final_error'] = failed_job_data['error']
                job.meta['platform'] = 'Windows'
                job.meta['failed_on_windows'] = True
                job.save_meta()
            
            # 데드 레터 큐에 저장
            self.dead_letter_queue.enqueue(
                self._dead_letter_placeholder,
                failed_job_data,
                job_timeout=self.config['dead_letter_ttl'],
                description=f"Windows Failed Job: {failed_job_data['job_id']}"
            )
            
            api_logger.error(f"작업 최종 실패, 데드 레터 큐 이동: {job.id}")
            
            # 스레드 풀로 최종 실패 로그 저장
            self.thread_pool.submit(
                self._save_final_failure_log_sync, 
                failed_job_data.copy()
            )
            
        except Exception as e:
            api_logger.error(f"데드 레터 이동 실패: {str(e)}")
    
    def _dead_letter_placeholder(self, failed_job_data: Dict[str, Any]):
        """데드 레터 큐 플레이스홀더 함수"""
        # Windows에서도 실제로는 실행되지 않음, 데이터 보관용
        api_logger.info(f"데드 레터 데이터 보관: {failed_job_data.get('job_id', 'unknown')}")
    
    def _get_db_failure_count(self, job_id: str) -> int:
        """DB에서 실패 횟수 조회 - Windows Redis 최적화"""
        try:
            # Redis 연결 풀 사용으로 Windows 연결 이슈 최소화
            failure_key = f"job_failures:{job_id}"
            count = self.redis_conn.get(failure_key)
            return int(count) if count else 0
        except (redis.ConnectionError, redis.TimeoutError) as e:
            api_logger.warning(f"Redis 연결 오류 (Windows): {str(e)}")
            return 0
        except Exception as e:
            api_logger.error(f"실패 횟수 조회 실패: {str(e)}")
            return 0
    
    def _save_retry_log_sync(self, failed_job_data: Dict[str, Any], retry_count: int):
        """재시도 로그 동기 저장 - 스레드 풀용"""
        try:
            # Redis에 실패 카운트 증가 (Windows 타임아웃 설정)
            failure_key = f"job_failures:{failed_job_data['job_id']}"
            
            with redis.Redis(
                connection_pool=self.redis_conn.connection_pool,
                socket_timeout=10,  # Windows 소켓 타임아웃
                socket_connect_timeout=5
            ) as redis_client:
                redis_client.incr(failure_key)
                redis_client.expire(failure_key, self.config['dead_letter_ttl'])
            
            # 로그 데이터 구조화
            retry_log = {
                'job_id': failed_job_data['job_id'],
                'retry_count': retry_count,
                'error_message': failed_job_data['error'],
                'retry_at': datetime.now().isoformat(),
                'status': 'retrying',
                'platform': 'Windows'
            }
            
            api_logger.info(f"재시도 로그 저장 완료: {retry_log['job_id']} (시도 {retry_count})")
            
            # TODO: Supabase webhook_operations 테이블에 저장하는 부분
            # Windows 환경에서는 별도 스레드 풀로 처리하여 안정성 확보
            
        except Exception as e:
            api_logger.error(f"재시도 로그 저장 실패: {str(e)}")
    
    def _save_final_failure_log_sync(self, failed_job_data: Dict[str, Any]):
        """최종 실패 로그 동기 저장 - 스레드 풀용"""
        try:
            final_log = {
                'job_id': failed_job_data['job_id'],
                'final_error': failed_job_data['error'],
                'total_retries': failed_job_data['retry_count'],
                'failed_at': failed_job_data['failed_at'],
                'status': 'failed_permanently',
                'platform': 'Windows'
            }
            
            api_logger.error(f"최종 실패 로그 저장 완료: {final_log['job_id']}")
            
            # TODO: Supabase webhook_operations 테이블에 저장
            
        except Exception as e:
            api_logger.error(f"최종 실패 로그 저장 실패: {str(e)}")
    
    def get_failure_statistics(self) -> Dict[str, Any]:
        """실패 통계 조회 - Windows 버전"""
        try:
            retry_queue_size = len(self.retry_queue)
            dead_letter_size = len(self.dead_letter_queue)
            
            return {
                'retry_queue_size': retry_queue_size,
                'dead_letter_queue_size': dead_letter_size,
                'thread_pool_active': self.thread_pool._threads,
                'platform': 'Windows',
                'config': self.config
            }
        except Exception as e:
            return {'error': f"통계 조회 실패: {str(e)}"}
    
    def cleanup(self):
        """리소스 정리 - Windows 버전"""
        try:
            self.thread_pool.shutdown(wait=True, timeout=30)
            api_logger.info("Windows DeadLetterHandler 정리 완료")
        except Exception as e:
            api_logger.error(f"리소스 정리 실패: {str(e)}")


# 전역 핸들러 함수 (RQ에서 직접 사용)
def handle_failed_job_win(job, exc_type, exc_value, traceback):
    """RQ 실패 핸들러 진입점 - Windows 버전"""
    try:
        # Redis 연결은 job에서 가져옴
        redis_conn = job.connection
        handler = DeadLetterHandlerWin(redis_conn)
        handler.handle_failed_job(job, exc_type, exc_value, traceback)
    except Exception as e:
        api_logger.error(f"Windows 실패 핸들러 오류: {str(e)}")

# 기존 함수명과의 호환성을 위한 별칭
handle_failed_job = handle_failed_job_win