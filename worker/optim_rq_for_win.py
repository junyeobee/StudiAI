import os
import time
import threading
import subprocess
import psutil
from typing import List, Dict, Any, Optional
from rq import Queue, Worker, SpawnWorker
from rq.worker import WorkerStatus
from app.utils.logger import api_logger
from worker.config import RQ_CONFIG
from worker.monitor import get_queue_stats, get_worker_health
from app.core.config import settings
import redis

class RQOptimizerForWin:
    """Windows 환경 전용 RQ 워커 동적 최적화 클래스"""
    
    def __init__(self, redis_conn: redis.Redis):
        self.redis_conn = redis_conn
        self.config = RQ_CONFIG['scaling']
        self.monitoring_config = RQ_CONFIG['monitoring']
        self.queue = Queue('code_analysis', connection=redis_conn)
        self.active_worker_processes: List[subprocess.Popen] = []
        self.worker_pids: List[int] = []  # PID 추적용
        self.is_monitoring = False
        self.lock = threading.Lock()  # 스레드 안전성
        
    def start_monitoring(self):
        """모니터링 시작 - Windows 스레드 안전"""
        with self.lock:
            if self.is_monitoring:
                api_logger.warning("모니터링이 이미 실행 중입니다.")
                return
                
            self.is_monitoring = True
            
        # daemon=True로 메인 프로세스 종료 시 자동 정리
        monitor_thread = threading.Thread(
            target=self._monitoring_loop, 
            daemon=True,
            name="RQOptimizer-Monitor"
        )
        monitor_thread.start()
        api_logger.info("Windows RQ 최적화 모니터링 시작")
    
    def stop_monitoring(self):
        """모니터링 중지"""
        with self.lock:
            self.is_monitoring = False
        api_logger.info("Windows RQ 최적화 모니터링 중지")
    
    def _monitoring_loop(self):
        """모니터링 루프 - Windows 안전 버전"""
        while self.is_monitoring:
            try:
                self._cleanup_dead_processes()  # 종료된 프로세스 먼저 정리
                self._check_and_scale()
                time.sleep(self.monitoring_config['health_check_interval'])
            except Exception as e:
                api_logger.error(f"모니터링 루프 오류: {str(e)}")
                time.sleep(10)  # 오류 시 10초 대기
    
    def _check_and_scale(self):
        """큐 상태 확인 및 스케일링 결정 - Windows 버전"""
        try:
            # 현재 상태 조회
            queue_size = len(self.queue)
            active_processes = self._count_active_processes()
            
            api_logger.debug(f"큐 크기: {queue_size}, 활성 프로세스: {active_processes}")
            
            # 스케일 업 조건 확인
            if (queue_size >= self.config['scale_up_threshold'] and 
                active_processes < self.config['max_workers']):
                self._scale_up()
                
            # 스케일 다운 조건 확인  
            elif (queue_size <= self.config['scale_down_threshold'] and 
                  active_processes > self.config['min_workers']):
                self._scale_down()
                
            # 알림 임계값 확인
            if queue_size >= self.monitoring_config['alert_threshold']:
                self._send_alert(queue_size, active_processes)
                
        except Exception as e:
            api_logger.error(f"스케일링 체크 오류: {str(e)}")
    
    def _scale_up(self):
        """워커 스케일 업 - Windows SpawnWorker 사용"""
        try:
            current_workers = self._count_active_processes()
            workers_to_add = min(
                self.config['scale_up_count'],
                self.config['max_workers'] - current_workers
            )
            
            if workers_to_add <= 0:
                return
                
            api_logger.info(f"워커 스케일 업: {workers_to_add}개 워커 추가")
            
            for i in range(workers_to_add):
                self._spawn_worker()
                
        except Exception as e:
            api_logger.error(f"스케일 업 실패: {str(e)}")
    
    def _scale_down(self):
        """워커 스케일 다운 - Windows 안전 종료"""
        try:
            current_workers = self._count_active_processes()
            workers_to_remove = min(
                self.config['scale_down_count'],
                current_workers - self.config['min_workers']
            )
            
            if workers_to_remove <= 0:
                return
                
            api_logger.info(f"워커 스케일 다운: {workers_to_remove}개 워커 제거")
            
            self._terminate_idle_workers(workers_to_remove)
            
        except Exception as e:
            api_logger.error(f"스케일 다운 실패: {str(e)}")
    
    def _spawn_worker(self):
        """새 워커 프로세스 생성 - Windows 최적화"""
        try:
            # 현재 스크립트 경로 기준으로 워커 실행
            current_dir = os.path.dirname(os.path.abspath(__file__))
            worker_script = os.path.join(current_dir, 'tasks.py')
            
            # Windows 환경변수 설정
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'  # 버퍼링 비활성화
            env['WORKER_MODE'] = 'spawn'   # SpawnWorker 모드
            
            # subprocess.Popen으로 새 프로세스 생성
            process = subprocess.Popen(
                [
                    'python', worker_script,
                    '--worker-class', 'SpawnWorker',  # Windows 권장
                    '--queue', 'code_analysis'
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            )
            
            with self.lock:
                self.active_worker_processes.append(process)
                self.worker_pids.append(process.pid)
            
            api_logger.info(f"새 워커 프로세스 생성: PID {process.pid}")
            
        except Exception as e:
            api_logger.error(f"워커 생성 실패: {str(e)}")
    
    def _terminate_idle_workers(self, count: int):
        """유휴 워커 종료 - Windows 안전 종료 방식"""
        try:
            terminated_count = 0
            
            with self.lock:
                processes_to_terminate = []
                
                # 살아있는 프로세스 중에서 유휴 상태인 것 찾기
                for process in self.active_worker_processes[:]:
                    if process.poll() is None:  # 프로세스가 살아있음
                        try:
                            # psutil로 프로세스 상태 확인
                            proc = psutil.Process(process.pid)
                            
                            # CPU 사용률이 낮으면 유휴 상태로 간주
                            cpu_percent = proc.cpu_percent(interval=1)
                            if cpu_percent < 5.0:  # 5% 미만이면 유휴
                                processes_to_terminate.append(process)
                                if len(processes_to_terminate) >= count:
                                    break
                                    
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            # 프로세스가 이미 종료되었거나 접근 권한 없음
                            processes_to_terminate.append(process)
                            continue
                
                # 선택된 프로세스들 안전하게 종료
                for process in processes_to_terminate:
                    try:
                        # 1단계: 정상 종료 시도 (SIGTERM 대신 Windows 방식)
                        process.terminate()
                        
                        # 2단계: 5초 대기
                        try:
                            process.wait(timeout=5)
                            api_logger.info(f"워커 프로세스 정상 종료: PID {process.pid}")
                        except subprocess.TimeoutExpired:
                            # 3단계: 강제 종료
                            process.kill()
                            process.wait()
                            api_logger.warning(f"워커 프로세스 강제 종료: PID {process.pid}")
                        
                        # 리스트에서 제거
                        if process in self.active_worker_processes:
                            self.active_worker_processes.remove(process)
                        if process.pid in self.worker_pids:
                            self.worker_pids.remove(process.pid)
                            
                        terminated_count += 1
                        
                    except Exception as e:
                        api_logger.error(f"워커 종료 실패 PID {process.pid}: {str(e)}")
            
            api_logger.info(f"{terminated_count}개 워커 종료 완료")
            
        except Exception as e:
            api_logger.error(f"워커 종료 실패: {str(e)}")
    
    def _count_active_processes(self) -> int:
        """활성 프로세스 수 조회 - Windows psutil 사용"""
        try:
            active_count = 0
            
            with self.lock:
                for pid in self.worker_pids[:]:
                    try:
                        if psutil.pid_exists(pid):
                            proc = psutil.Process(pid)
                            if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                                active_count += 1
                        else:
                            # PID가 존재하지 않으면 리스트에서 제거
                            self.worker_pids.remove(pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        self.worker_pids.remove(pid)
                        
            return active_count
            
        except Exception as e:
            api_logger.error(f"활성 프로세스 카운트 실패: {str(e)}")
            return 0
    
    def _cleanup_dead_processes(self):
        """종료된 프로세스 정리 - Windows 버전"""
        with self.lock:
            active_processes = []
            active_pids = []
            
            for process in self.active_worker_processes:
                if process.poll() is None:  # 아직 실행 중
                    active_processes.append(process)
                    active_pids.append(process.pid)
                else:  # 종료됨
                    api_logger.debug(f"종료된 프로세스 정리: PID {process.pid}")
            
            self.active_worker_processes = active_processes
            self.worker_pids = active_pids
    
    def _send_alert(self, queue_size: int, worker_count: int):
        """알림 전송 - Windows 이벤트 로그 활용 가능"""
        alert_message = f"⚠️ RQ 큐 알림: 큐 크기 {queue_size}, 워커 수 {worker_count}"
        api_logger.warning(alert_message)
        
        # Windows 이벤트 로그에 기록 (선택사항)
        try:
            import win32evtlog
            import win32evtlogutil
            
            win32evtlogutil.ReportEvent(
                "RQ Worker",
                1,  # Event ID
                eventCategory=0,
                eventType=win32evtlog.EVENTLOG_WARNING_TYPE,
                strings=[alert_message]
            )
        except ImportError:
            # win32api가 없어도 계속 실행
            pass
    
    def get_optimization_stats(self) -> Dict[str, Any]:
        """최적화 통계 조회 - Windows 버전"""
        try:
            queue_stats = get_queue_stats(self.redis_conn)
            
            return {
                '모니터링_상태': 'active' if self.is_monitoring else 'inactive',
                '큐_통계': queue_stats,
                '스케일링_설정': self.config,
                '활성_프로세스_수': self._count_active_processes(),
                '등록된_PID_수': len(self.worker_pids),
                '최적화_상태': self._get_optimization_status(),
                '플랫폼': 'Windows',
                '워커_타입': 'SpawnWorker'
            }
        except Exception as e:
            return {'오류': f"통계 조회 실패: {str(e)}"}
    
    def _get_optimization_status(self) -> str:
        """최적화 상태 평가"""
        try:
            queue_size = len(self.queue)
            worker_count = self._count_active_processes()
            
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
    
    def shutdown_all_workers(self):
        """모든 워커 안전 종료 - Windows 버전"""
        api_logger.info("모든 워커 종료 시작...")
        
        with self.lock:
            for process in self.active_worker_processes[:]:
                try:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        api_logger.info(f"워커 프로세스 종료 완료: PID {process.pid}")
                except Exception as e:
                    api_logger.error(f"워커 종료 실패 PID {process.pid}: {str(e)}")
            
            self.active_worker_processes.clear()
            self.worker_pids.clear()
        
        api_logger.info("모든 워커 종료 완료")


# 전역 함수들 (기존 호환성 유지)
def smart_worker_scaling():
    """큐 길이에 따른 동적 워커 스케일링 (Windows 레거시 함수)"""
    try:
        redis_conn = redis.Redis(
            host=settings.REDIS_HOST,
            port=int(settings.REDIS_PORT),
            password=settings.REDIS_PASSWORD
        )
        
        optimizer = RQOptimizerForWin(redis_conn)
        optimizer._check_and_scale()
        
    except Exception as e:
        api_logger.error(f"Windows 스케일링 실패: {str(e)}")

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
    """추가 워커 생성 (Windows 버전)"""
    try:
        redis_conn = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            password=os.getenv('REDIS_PASSWORD', None)
        )
        optimizer = RQOptimizerForWin(redis_conn)
        for _ in range(count):
            optimizer._spawn_worker()
    except Exception as e:
        api_logger.error(f"Windows 워커 생성 실패: {str(e)}")