import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any
from rq import Queue
from rq.job import Job
from worker.config import RQ_CONFIG
from app.utils.logger import api_logger
import redis

class DeadLetterHandler:
    """실패한 작업 처리 클래스"""
    
    def __init__(self, redis_conn: redis.Redis):
        self.redis_conn = redis_conn
        self.config = RQ_CONFIG['failure']
        self.retry_queue = Queue('retry_queue', connection=redis_conn)
        self.dead_letter_queue = Queue('dead_letter_queue', connection=redis_conn)
    
    def handle_failed_job(self, job: Job, exc_type, exc_value, traceback):
        """실패한 작업 처리 메인 로직"""
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
        """작업 데이터 추출"""
        return {
            'job_id': job.id,
            'function_name': job.func_name,
            'args': job.args,
            'kwargs': job.kwargs,
            'error': str(exc_value),
            'retry_count': job.meta.get('retry_count', 0),
            'failed_at': datetime.now().isoformat(),
            'queue_name': job.origin
        }
    
    def _should_retry(self, failed_job_data: Dict[str, Any]) -> bool:
        """재시도 가능 여부 확인"""
        retry_count = failed_job_data['retry_count']
        max_retries = self.config['max_retries']
        
        # DB 실패 횟수도 확인
        db_failure_count = self._get_db_failure_count(failed_job_data['job_id'])
        max_db_failures = self.config['max_db_failures']
        
        return (retry_count < max_retries and 
                db_failure_count < max_db_failures)
    
    def _schedule_retry(self, job: Job, failed_job_data: Dict[str, Any]):
        """재시도 스케줄링"""
        retry_count = failed_job_data['retry_count'] + 1
        retry_delay = self.config['retry_delay'] * retry_count  # 지수 백오프
        
        # 메타데이터 업데이트
        job.meta['retry_count'] = retry_count
        job.meta['last_failure'] = failed_job_data['failed_at']
        job.meta['last_error'] = failed_job_data['error']
        job.save_meta()
        
        # 재시도 큐에 지연 등록
        self.retry_queue.enqueue_in(
            timedelta(seconds=retry_delay),
            job.func,
            *job.args,
            **job.kwargs,
            job_id=f"{job.id}_retry_{retry_count}",
            meta=job.meta
        )
        
        api_logger.info(f"작업 재시도 예약: {job.id} (시도 {retry_count}/{self.config['max_retries']})")
        
        # DB에 재시도 로그 저장
        asyncio.create_task(self._save_retry_log(failed_job_data, retry_count))
    
    def _move_to_dead_letter(self, job: Job, failed_job_data: Dict[str, Any]):
        """데드 레터 큐로 이동"""
        # 최종 실패 메타데이터 추가
        job.meta['final_failure'] = True
        job.meta['total_retries'] = failed_job_data['retry_count']
        job.meta['final_error'] = failed_job_data['error']
        job.save_meta()
        
        # 데드 레터 큐에 저장
        self.dead_letter_queue.enqueue(
            self._dead_letter_placeholder,
            failed_job_data,
            job_timeout=self.config['dead_letter_ttl']
        )
        
        api_logger.error(f"작업 최종 실패, 데드 레터 큐 이동: {job.id}")
        
        # DB에 최종 실패 로그 저장
        asyncio.create_task(self._save_final_failure_log(failed_job_data))
    
    def _dead_letter_placeholder(self, failed_job_data: Dict[str, Any]):
        """데드 레터 큐 플레이스홀더 함수"""
        # 실제로는 실행되지 않음, 데이터 보관용
        pass
    
    def _get_db_failure_count(self, job_id: str) -> int:
        """DB에서 실패 횟수 조회"""
        try:
            # Redis에서 실패 카운트 조회
            failure_key = f"job_failures:{job_id}"
            count = self.redis_conn.get(failure_key)
            return int(count) if count else 0
        except Exception:
            return 0
    
    async def _save_retry_log(self, failed_job_data: Dict[str, Any], retry_count: int):
        """재시도 로그 DB 저장"""
        try:
            # Redis에 실패 카운트 증가
            failure_key = f"job_failures:{failed_job_data['job_id']}"
            self.redis_conn.incr(failure_key)
            self.redis_conn.expire(failure_key, self.config['dead_letter_ttl'])
            
            # TODO: Supabase webhook_operations 테이블에 재시도 로그 저장
            retry_log = {
                'job_id': failed_job_data['job_id'],
                'retry_count': retry_count,
                'error_message': failed_job_data['error'],
                'retry_at': datetime.now().isoformat(),
                'status': 'retrying'
            }
            
            api_logger.info(f"재시도 로그 저장: {retry_log}")
            
        except Exception as e:
            api_logger.error(f"재시도 로그 저장 실패: {str(e)}")
    
    async def _save_final_failure_log(self, failed_job_data: Dict[str, Any]):
        """최종 실패 로그 DB 저장"""
        try:
            # TODO: Supabase webhook_operations 테이블에 최종 실패 로그 저장
            final_log = {
                'job_id': failed_job_data['job_id'],
                'final_error': failed_job_data['error'],
                'total_retries': failed_job_data['retry_count'],
                'failed_at': failed_job_data['failed_at'],
                'status': 'failed_permanently'
            }
            
            api_logger.error(f"최종 실패 로그 저장: {final_log}")
            
        except Exception as e:
            api_logger.error(f"최종 실패 로그 저장 실패: {str(e)}")

# 전역 핸들러 함수 (RQ에서 직접 사용)
def handle_failed_job(job, exc_type, exc_value, traceback):
    """RQ 실패 핸들러 진입점"""
    # Redis 연결은 job에서 가져옴
    redis_conn = job.connection
    handler = DeadLetterHandler(redis_conn)
    handler.handle_failed_job(job, exc_type, exc_value, traceback)