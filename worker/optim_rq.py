import os
import time
import threading
import subprocess
from typing import List, Dict, Any
from rq import Queue, Worker
from worker.config import RQ_CONFIG
from worker.monitor import get_queue_stats, get_worker_health, is_worker_idle, get_worker_state_name
from app.utils.logger import api_logger
import redis

class RQOptimizer:
    """RQ 워커 동적 최적화 클래스"""
    
    def __init__(self, redis_conn: redis.Redis):
        self.redis_conn = redis_conn
        self.config = RQ_CONFIG['scaling']
        self.monitoring_config = RQ_CONFIG['monitoring']
        self.queue = Queue('code_analysis', connection=redis_conn)
        self.active_worker_processes: List[subprocess.Popen] = []
        self.is_monitoring = False
        
    def start_monitoring(self):
        """모니터링 시작"""
        if self.is_monitoring:
            api_logger.warning("모니터링이 이미 실행 중입니다.")
            return
            
        self.is_monitoring = True
        monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        monitor_thread.start()
        api_logger.info("RQ 최적화 모니터링 시작")
    
    def stop_monitoring(self):
        """모니터링 중지"""
        self.is_monitoring = False
        api_logger.info("RQ 최적화 모니터링 중지")
    
    def _monitoring_loop(self):
        """모니터링 루프"""
        while self.is_monitoring:
            try:
                self._check_and_scale()
                time.sleep(self.monitoring_config['health_check_interval'])
            except Exception as e:
                api_logger.error(f"모니터링 루프 오류: {str(e)}")
                time.sleep(10)  # 오류 시 10초 대기
    
    def _check_and_scale(self):
        """큐 상태 확인 및 스케일링 결정"""
        try:
            # 현재 상태 조회
            queue_size = len(self.queue)
            health_data = get_worker_health(self.redis_conn)
            current_workers = health_data.get('total_workers', 0)
            
            api_logger.debug(f"큐 크기: {queue_size}, 현재 워커: {current_workers}")
            
            # 스케일 업 조건 확인
            if (queue_size >= self.config['scale_up_threshold'] and 
                current_workers < self.config['max_workers']):
                self._scale_up()
                
            # 스케일 다운 조건 확인
            elif (queue_size <= self.config['scale_down_threshold'] and 
                  current_workers > self.config['min_workers']):
                self._scale_down()
                
            # 알림 임계값 확인
            if queue_size >= self.monitoring_config['alert_threshold']:
                self._send_alert(queue_size, current_workers)
                
        except Exception as e:
            api_logger.error(f"스케일링 체크 오류: {str(e)}")
    
    def _scale_up(self):
        """워커 스케일 업"""
        try:
            workers_to_add = min(
                self.config['scale_up_count'],
                self.config['max_workers'] - self._get_current_worker_count()
            )
            
            if workers_to_add <= 0:
                return
                
            api_logger.info(f"워커 스케일 업: {workers_to_add}개 워커 추가")
            
            for i in range(workers_to_add):
                self._spawn_worker()
                
        except Exception as e:
            api_logger.error(f"스케일 업 실패: {str(e)}")
    
    def _scale_down(self):
        """워커 스케일 다운"""
        try:
            workers_to_remove = min(
                self.config['scale_down_count'],
                self._get_current_worker_count() - self.config['min_workers']
            )
            
            if workers_to_remove <= 0:
                return
                
            api_logger.info(f"워커 스케일 다운: {workers_to_remove}개 워커 제거")
            
            self._terminate_idle_workers(workers_to_remove)
            
        except Exception as e:
            api_logger.error(f"스케일 다운 실패: {str(e)}")
    
    def _spawn_worker(self):
        """새 워커 프로세스 생성"""
        try:
            # 현재 스크립트 경로 기준으로 워커 실행
            worker_script = os.path.join(os.path.dirname(__file__), 'tasks.py')
            
            process = subprocess.Popen(
                ['python', worker_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            self.active_worker_processes.append(process)
            api_logger.info(f"새 워커 프로세스 생성: PID {process.pid}")
            
        except Exception as e:
            api_logger.error(f"워커 생성 실패: {str(e)}")
    
    def _terminate_idle_workers(self, count: int):
        """유휴 워커 종료 - 안전한 상태 확인 사용"""
        try:
            # RQ 워커에서 유휴 상태인 워커 찾기 - 안전한 방식 사용
            workers = Worker.all(connection=self.redis_conn)
            idle_workers = [w for w in workers if is_worker_idle(w)]
            
            terminated_count = 0
            for worker in idle_workers[:count]:
                try:
                    # 워커에게 종료 신호 전송
                    worker.request_stop()
                    api_logger.info(f"워커 종료 요청: {worker.name} (상태: {get_worker_state_name(worker)})")
                    terminated_count += 1
                except Exception as e:
                    api_logger.error(f"워커 종료 실패 {worker.name}: {str(e)}")
            
            # 프로세스 정리
            self._cleanup_terminated_processes()
            
            api_logger.info(f"{terminated_count}개 워커 종료 완료")
            
        except Exception as e:
            api_logger.error(f"워커 종료 실패: {str(e)}")
    
    def _cleanup_terminated_processes(self):
        """종료된 프로세스 정리"""
        active_processes = []
        
        for process in self.active_worker_processes:
            if process.poll() is None:  # 아직 실행 중
                active_processes.append(process)
            else:  # 종료됨
                api_logger.debug(f"프로세스 정리: PID {process.pid}")
        
        self.active_worker_processes = active_processes
    
    def _get_current_worker_count(self) -> int:
        """현재 워커 수 조회"""
        try:
            workers = Worker.all(connection=self.redis_conn)
            return len(workers)
        except Exception:
            return 0
    
    def _send_alert(self, queue_size: int, worker_count: int):
        """알림 전송"""
        alert_message = f"⚠️ RQ 큐 알림: 큐 크기 {queue_size}, 워커 수 {worker_count}"
        api_logger.warning(alert_message)
        
        # TODO: 실제 알림 시스템 연동 (Slack, 이메일 등)
        # 예: send_slack_notification(alert_message)
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """최적화 통계 조회"""
        try:
            queue_stats = get_queue_stats(self.redis_conn)
            health_data = get_worker_health(self.redis_conn)
            
            return {
                '모니터링_상태': 'active' if self.is_monitoring else 'inactive',
                '큐_통계': queue_stats,
                '워커_헬스': health_data,
                '스케일링_설정': self.config,
                '활성_프로세스_수': len(self.active_worker_processes),
                '최적화_상태': self._get_optimization_status()
            }
        except Exception as e:
            return {'오류': f"통계 조회 실패: {str(e)}"}
    
    def _get_optimization_status(self) -> str:
        """최적화 상태 평가"""
        try:
            queue_size = len(self.queue)
            worker_count = self._get_current_worker_count()
            
            if queue_size == 0:
                return 'idle'
            elif queue_size < self.config['scale_up_threshold']:
                return 'optimal'
            elif worker_count < self.config['max_workers']:
                return 'scaling_needed'
            else:
                return 'at_capacity'
        except Exception:
            return 'unknown'

# 전역 함수들 (기존 호환성 유지)
def smart_worker_scaling():
    """큐 길이에 따른 동적 워커 스케일링 (레거시 함수)"""
    try:
        # Redis 연결 생성 (환경변수에서)
        redis_conn = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            password=os.getenv('REDIS_PASSWORD', None)
        )
        
        optimizer = RQOptimizer(redis_conn)
        optimizer._check_and_scale()
        
    except Exception as e:
        api_logger.error(f"레거시 스케일링 실패: {str(e)}")

def get_queue_size() -> int:
    """큐 크기 조회 (레거시 함수)"""
    try:
        redis_conn = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            password=os.getenv('REDIS_PASSWORD', None)
        )
        queue = Queue('code_analysis', connection=redis_conn)
        return len(queue)
    except Exception:
        return 0

def spawn_additional_workers(count: int):
    """추가 워커 생성 (레거시 함수)"""
    try:
        redis_conn = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            password=os.getenv('REDIS_PASSWORD', None)
        )
        optimizer = RQOptimizer(redis_conn)
        for _ in range(count):
            optimizer._spawn_worker()
    except Exception as e:
        api_logger.error(f"워커 생성 실패: {str(e)}")

def terminate_idle_workers(count: int):
    """유휴 워커 종료 (레거시 함수)"""
    try:
        redis_conn = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            password=os.getenv('REDIS_PASSWORD', None)
        )
        optimizer = RQOptimizer(redis_conn)
        optimizer._terminate_idle_workers(count)
    except Exception as e:
        api_logger.error(f"워커 종료 실패: {str(e)}")