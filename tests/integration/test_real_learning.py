import asyncio
import sys
from pathlib import Path
import logging

# 프로젝트 루트 디렉터리를 Python 경로에 추가
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent  # tests/integration/ -> tests/ -> 루트
sys.path.insert(0, str(project_root))

from app.services.extract_for_file_service import extract_functions_by_type, ExtractorRegistry

# 로그 레벨을 DEBUG로 설정
logging.getLogger('api').setLevel(logging.DEBUG)

async def test_learning_file():
    # learning.py 파일 읽기
    with open('app/api/v1/endpoints/learning.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    print('📁 파일:', 'app/api/v1/endpoints/learning.py')
    print('📏 파일 크기:', len(content), '바이트')
    print('📄 라인 수:', len(content.splitlines()), '줄')
    print()
    
    # 함수 추출 실행 (DEBUG 로그 포함)
    print('🔧 함수 추출 시작 (DEBUG 모드):')
    print('=' * 60)
    
    functions = await extract_functions_by_type(content, 'learning.py', {})
    
    print()
    print('📊 추출 결과:')
    for i, func in enumerate(functions, 1):
        icon = '🎯' if func['name'] == 'get_commit_details' else '📋'
        print(f'{i:2d}. {icon} {func["name"]:25} | {func["type"]:10} | {func["start_line"]:3d}-{func["end_line"]:3d} 라인')
        
        # get_commit_details인 경우 코드 첫 줄 확인
        if func['name'] == 'get_commit_details':
            first_line = func['code'].split('\n')[0].strip()
            print(f"     📝 첫 줄: {first_line}")

if __name__ == "__main__":
    asyncio.run(test_learning_file()) 