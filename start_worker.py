"""
Celery 워커 실행 스크립트
"""

import os
import sys

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from worker.tasks import app

if __name__ == '__main__':
    # Celery 워커 실행
    app.worker_main([
        'worker',
        '--loglevel=info',
        '--concurrency=4'
    ]) 