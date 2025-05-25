"""
RQ 워커 실행 스크립트
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from worker.tasks import start_worker

if __name__ == '__main__':
    start_worker() 