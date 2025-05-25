from celery import Celery
from typing import Dict, List, Any
import asyncio
import redis
from urllib.parse import quote_plus
from app.services.code_analysis_service import CodeAnalysisService
from app.core.config import settings
from app.utils.logger import api_logger

# Redis 설정 값들을 적절한 타입으로 변환
redis_host = settings.REDIS_HOST
redis_port = int(settings.REDIS_PORT)
redis_password = settings.REDIS_PASSWORD

# Redis 패스워드 URL 인코딩 (특수문자 처리)
encoded_password = quote_plus(redis_password)

# Celery 앱 초기화 - URL 인코딩된 패스워드 사용
app = Celery('worker', broker=f'redis://:{encoded_password}@{redis_host}:{redis_port}/0')

# Redis 클라이언트 (원본 패스워드 사용)
redis_client = redis.Redis(host=redis_host, port=redis_port, password=redis_password)

@app.task
def analyze_code_task(files: List[Dict], owner: str, repo: str, commit_sha: str, user_id: str):
    """코드 분석 태스크 - 워커에서 실행"""
    try:
        api_logger.info(f"워커에서 코드 분석 시작: {commit_sha[:8]}, 파일 수: {len(files)}")
        
        # 비동기 함수를 동기적으로 실행
        asyncio.run(_analyze_code_async(files, owner, repo, commit_sha, user_id))
        
        api_logger.info(f"워커에서 코드 분석 완료: {commit_sha[:8]}")
        return {"status": "success", "commit_sha": commit_sha}
        
    except Exception as e:
        api_logger.error(f"워커 코드 분석 실패: {str(e)}")
        return {"status": "error", "error": str(e)}

async def _analyze_code_async(files: List[Dict], owner: str, repo: str, commit_sha: str, user_id: str):
    """비동기 코드 분석 실행"""
    from supabase import create_client
    
    # Supabase 클라이언트 생성 (비동기)
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
    
    # 분석 서비스 초기화
    analysis_service = CodeAnalysisService(redis_client, supabase)
    
    # 코드 변경 분석
    await analysis_service.analyze_code_changes(
        files=files,
        owner=owner,
        repo=repo,
        commit_sha=commit_sha,
        user_id=user_id
    )
    
    # 큐 처리
    await analysis_service.process_queue() 