import redis
import asyncio
import os
from typing import Dict, List, Any
from rq import Queue, SimpleWorker
from rq.timeouts import TimerDeathPenalty
from app.services.code_analysis_service import CodeAnalysisService
from app.core.config import settings
from app.utils.logger import api_logger

# Windows 호환 워커 클래스 정의
class WindowsSimpleWorker(SimpleWorker):
    """Windows에서 SIGALRM 신호 문제를 해결하는 워커"""
    death_penalty_class = TimerDeathPenalty

# Redis 설정
redis_host = settings.REDIS_HOST
redis_port = int(settings.REDIS_PORT)
redis_password = settings.REDIS_PASSWORD

# Redis 연결
redis_conn = redis.Redis(host=redis_host, port=redis_port, password=redis_password)

# RQ 큐 생성
task_queue = Queue('code_analysis', connection=redis_conn)

def analyze_code_task(files: List[Dict], owner: str, repo: str, commit_sha: str, user_id: str):
    """코드 분석 태스크 - RQ 워커에서 실행"""
    try:
        api_logger.info(f"RQ 워커에서 코드 분석 시작: {commit_sha[:8]}, 파일 수: {len(files)}")
        api_logger.info(f"사용자 ID: {user_id}, 저장소: {owner}/{repo}")
        
        # 비동기 함수를 동기적으로 실행
        asyncio.run(_analyze_code_async(files, owner, repo, commit_sha, user_id))
        
        api_logger.info(f"RQ 워커 코드 분석 완료: {commit_sha[:8]}")
        return {"status": "success", "commit_sha": commit_sha}
        
    except Exception as e:
        api_logger.error(f"RQ 워커 코드 분석 실패: {str(e)}")
        raise e

async def _analyze_code_async(files: List[Dict], owner: str, repo: str, commit_sha: str, user_id: str):
    """비동기 코드 분석 실행"""
    try:
        from supabase import create_client
        
        api_logger.info("Supabase 클라이언트 생성 중...")
        # Supabase 클라이언트 생성
        supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        
        api_logger.info("분석 서비스 초기화 중...")
        # 분석 서비스 초기화
        analysis_service = CodeAnalysisService(redis_conn, supabase)
        
        api_logger.info("코드 변경 분석 시작...")
        # 코드 변경 분석
        await analysis_service.analyze_code_changes(
            files=files,
            owner=owner,
            repo=repo,
            commit_sha=commit_sha,
            user_id=user_id
        )
        
        api_logger.info("큐 처리 시작...")
        # 큐 처리
        await analysis_service.process_queue()
        
        api_logger.info("분석 완료")
        
    except Exception as e:
        api_logger.error(f"비동기 분석 실행 오류: {str(e)}")
        raise

def start_worker():
    """RQ 워커 시작 - Windows 완전 호환"""
    try:
        api_logger.info("RQ 워커 시작...")
        
        # Windows에서는 WindowsSimpleWorker 사용 (SIGALRM 문제 해결)
        if os.name == 'nt':  # Windows
            worker = WindowsSimpleWorker([task_queue], connection=redis_conn)
            api_logger.info("Windows용 WindowsSimpleWorker로 작업을 기다리고 있습니다...")
        else:  # Unix/Linux
            from rq import Worker
            worker = Worker([task_queue], connection=redis_conn)
            api_logger.info("RQ 워커가 작업을 기다리고 있습니다...")
        
        worker.work()
            
    except Exception as e:
        api_logger.error(f"RQ 워커 시작 실패: {str(e)}")
        raise

if __name__ == '__main__':
    start_worker() 