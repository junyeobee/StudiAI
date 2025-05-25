import os

# RQ 워커 기본 설정
WORKER_CONFIG = {
    'max_jobs': 10,  # 워커당 최대 동시 작업
    'timeout': 300,  # 5분 타임아웃
    'result_ttl': 86400,  # 결과 보관 24시간
    'job_timeout': 600,  # 개별 작업 타임아웃 (10분)
    'default_worker_ttl': 420,  # 워커 기본 TTL (7분)
}

# 실패 처리 설정
FAILURE_CONFIG = {
    'max_retries': 3,  # 최대 재시도 횟수
    'retry_delay': 60,  # 재시도 간격 (초)
    'max_db_failures': 5,  # DB 저장 최대 실패 횟수
    'dead_letter_ttl': 86400 * 7,  # 실패 작업 보관 기간 (7일)
}

# 동적 스케일링 설정
SCALING_CONFIG = {
    'scale_up_threshold': 50,  # 스케일 업 임계값
    'scale_down_threshold': 5,  # 스케일 다운 임계값
    'max_workers': 5,  # 최대 워커 수
    'min_workers': 1,  # 최소 워커 수
    'scale_up_count': 2,  # 스케일 업 시 추가할 워커 수
    'scale_down_count': 1,  # 스케일 다운 시 제거할 워커 수
}

# 모니터링 설정
MONITORING_CONFIG = {
    'health_check_interval': 30,  # 헬스 체크 간격 (초)
    'metrics_retention': 3600,  # 메트릭 보관 시간 (1시간)
    'alert_threshold': 100,  # 알림 임계값 (큐 크기)
}

# 환경별 설정 오버라이드
if os.getenv('ENVIRONMENT') == 'production':
    WORKER_CONFIG.update({
        'max_jobs': 20,
        'timeout': 600,  # 10분
        'job_timeout': 1200,  # 20분
    })
    SCALING_CONFIG.update({
        'max_workers': 10,
        'scale_up_threshold': 100,
    })

# 전체 설정 통합
RQ_CONFIG = {
    'worker': WORKER_CONFIG,
    'failure': FAILURE_CONFIG,
    'scaling': SCALING_CONFIG,
    'monitoring': MONITORING_CONFIG,
}