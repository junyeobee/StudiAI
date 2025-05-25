import redis
from rq import Queue, Worker
from rq.registry import StartedJobRegistry, FinishedJobRegistry, FailedJobRegistry
from rq.worker import WorkerStatus
from typing import Dict, Any

def get_worker_state_name(worker) -> str:
    """워커 상태를 안전하게 문자열로 변환"""
    try:
        if hasattr(worker.state, 'name'):
            return worker.state.name
        elif hasattr(worker.state, 'value'):
            return worker.state.value
        else:
            return str(worker.state)
    except Exception:
        return 'unknown'

def is_worker_busy(worker) -> bool:
    """워커가 바쁜 상태인지 확인"""
    try:
        if hasattr(worker, 'state'):
            state = worker.state
            # WorkerStatus enum 사용
            if hasattr(WorkerStatus, 'BUSY'):
                return state == WorkerStatus.BUSY
            # 문자열 비교
            state_str = get_worker_state_name(worker)
            return state_str.lower() in ['busy', 'working']
        return False
    except Exception:
        return False

def is_worker_idle(worker) -> bool:
    """워커가 유휴 상태인지 확인"""
    try:
        if hasattr(worker, 'state'):
            state = worker.state
            # WorkerStatus enum 사용
            if hasattr(WorkerStatus, 'IDLE'):
                return state == WorkerStatus.IDLE
            # 문자열 비교
            state_str = get_worker_state_name(worker)
            return state_str.lower() in ['idle', 'waiting']
        return False
    except Exception:
        return False

def get_queue_stats(redis_client: redis.Redis) -> Dict[str, Any]:
    """큐 상태 모니터링 - RQ 최신 API 사용"""
    try:
        queue = Queue('code_analysis', connection=redis_client)
        
        # 레지스트리 생성
        started_registry = StartedJobRegistry(queue=queue)
        finished_registry = FinishedJobRegistry(queue=queue)
        failed_registry = FailedJobRegistry(queue=queue)
        
        # Worker 통계 - 안전한 상태 확인
        all_workers = Worker.all(connection=redis_client)
        active_workers = [w for w in all_workers if is_worker_busy(w)]
        idle_workers = [w for w in all_workers if is_worker_idle(w)]
        
        # 큐 통계
        stats = {
            '큐_이름': queue.name,
            '대기중_작업': len(queue),
            '실행중_작업': len(started_registry),
            '완료된_작업': len(finished_registry),
            '실패한_작업': len(failed_registry),
            '전체_워커수': len(all_workers),
            '활성_워커수': len(active_workers),
            '대기_워커수': len(idle_workers),
            '큐_상태': 'active' if len(all_workers) > 0 else 'inactive'
        }
        
        # 활성 워커 상세 정보
        worker_info = []
        for worker in all_workers:
            try:
                current_job = None
                try:
                    job = worker.get_current_job()
                    current_job = job.id if job else None
                except Exception:
                    current_job = None
                
                worker_info.append({
                    '워커_이름': worker.name,
                    '상태': get_worker_state_name(worker),
                    '성공한_작업': getattr(worker, 'successful_job_count', 0),
                    '실패한_작업': getattr(worker, 'failed_job_count', 0),
                    '총_작업시간': f"{worker.total_working_time}초" if hasattr(worker, 'total_working_time') and worker.total_working_time else "0초",
                    '현재_작업': current_job
                })
            except Exception as e:
                worker_info.append({
                    '워커_이름': getattr(worker, 'name', 'unknown'),
                    '상태': 'error',
                    '오류': str(e)
                })
        
        stats['워커_상세정보'] = worker_info
        
        return stats
        
    except Exception as e:
        return {
            '오류': f"모니터링 실패: {str(e)}",
            '큐_상태': 'error'
        }

def get_detailed_queue_info(redis_client: redis.Redis) -> Dict[str, Any]:
    """상세한 큐 정보 조회"""
    try:
        queue = Queue('code_analysis', connection=redis_client)
        
        # 최근 작업들 조회
        started_registry = StartedJobRegistry(queue=queue)
        finished_registry = FinishedJobRegistry(queue=queue)
        failed_registry = FailedJobRegistry(queue=queue)
        
        recent_jobs = {
            '실행중_작업_ID들': list(started_registry.get_job_ids()),
            '최근_완료_작업_ID들': list(finished_registry.get_job_ids()[:5]),  # 최근 5개
            '최근_실패_작업_ID들': list(failed_registry.get_job_ids()[:5])   # 최근 5개
        }
        
        return recent_jobs
        
    except Exception as e:
        return {'오류': f"상세 정보 조회 실패: {str(e)}"}

def get_worker_health(redis_client: redis.Redis) -> Dict[str, Any]:
    """워커 헬스 체크 - 안전한 상태 확인"""
    try:
        queue = Queue('code_analysis', connection=redis_client)
        workers = Worker.all(connection=redis_client)
        
        # 안전한 워커 상태 카운트
        active_count = sum(1 for w in workers if is_worker_busy(w))
        idle_count = sum(1 for w in workers if is_worker_idle(w))
        
        return {
            'active_workers': active_count,
            'idle_workers': idle_count,
            'queue_size': len(queue),
            'total_workers': len(workers),
            'status': 'healthy' if len(workers) > 0 else 'no_workers'
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e)
        }

def print_queue_status(redis_client: redis.Redis):
    """큐 상태를 콘솔에 출력"""
    stats = get_queue_stats(redis_client)
    
    print("=" * 50)
    print("🔍 RQ 큐 모니터링 상태")
    print("=" * 50)
    
    for key, value in stats.items():
        if key == '워커_상세정보':
            print(f"\n👷 {key}:")
            if isinstance(value, list) and value:
                for i, worker in enumerate(value, 1):
                    print(f"  {i}. {worker}")
            else:
                print("  활성 워커 없음")
        else:
            print(f"📊 {key}: {value}")
    
    print("=" * 50)

if __name__ == '__main__':
    # 테스트용 Redis 연결
    import os
    redis_conn = redis.Redis(
        host=os.getenv('REDIS_HOST', 'localhost'),
        port=int(os.getenv('REDIS_PORT', 6379)),
        password=os.getenv('REDIS_PASSWORD', None)
    )
    
    print_queue_status(redis_conn)
    
    print("\n📋 상세 작업 정보:")
    detailed_info = get_detailed_queue_info(redis_conn)
    for key, value in detailed_info.items():
        print(f"  {key}: {value}")