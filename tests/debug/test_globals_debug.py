import asyncio
import logging
import sys
from pathlib import Path

# 프로젝트 루트 디렉터리를 Python 경로에 추가
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent  # tests/debug/ -> tests/ -> 루트
sys.path.insert(0, str(project_root))

from app.services.extract_for_file_service import extract_functions_by_type

# 디버그 로깅 활성화
logging.getLogger('api').setLevel(logging.DEBUG)

async def debug_globals_issue():
    """globals_and_imports 문제 상세 디버깅"""
    
    print("🔍 globals_and_imports 디버깅")
    print("=" * 60)
    
    # 간단한 테스트 파일로 시작
    simple_test_content = '''import os
import sys
from typing import List

# 전역 상수
CONSTANT_VALUE = "test"

def simple_function():
    """간단한 함수"""
    return "hello"

class SimpleClass:
    """간단한 클래스"""
    
    def method(self):
        return "world"

# 전역 변수
global_var = 42
'''
    
    print("📋 1. 간단한 테스트 케이스")
    print("-" * 40)
    
    functions = await extract_functions_by_type(simple_test_content, 'simple_test.py', {})
    
    print(f"📊 추출된 함수 목록:")
    lines = simple_test_content.splitlines()
    total_lines = len(lines)
    
    # 함수 범위 수집
    function_lines = set()
    for func in functions:
        if func['name'] != 'globals_and_imports':
            start = func['start_line']
            end = func['end_line']
            print(f"  📋 {func['name']:20} | {func['type']:10} | {start:2d}-{end:2d} 라인")
            function_lines.update(range(start, end + 1))
    
    # globals_and_imports 분석
    globals_func = next((f for f in functions if f['name'] == 'globals_and_imports'), None)
    if globals_func:
        print(f"\n📊 globals_and_imports 분석:")
        print(f"  범위: {globals_func['start_line']}-{globals_func['end_line']} 라인")
        print(f"  코드 길이: {len(globals_func['code'])} 문자")
        print(f"  빈 코드 여부: {not globals_func['code'].strip()}")
        
        if globals_func['code'].strip():
            print(f"  📝 전역 코드 미리보기:")
            global_lines = globals_func['code'].split('\n')[:5]
            for i, line in enumerate(global_lines, 1):
                print(f"    {i}: {repr(line)}")
    
    print(f"\n📈 범위 분석:")
    print(f"  총 라인 수: {total_lines}")
    print(f"  함수 범위 라인 수: {len(function_lines)}")
    print(f"  전역 범위 라인 수: {total_lines - len(function_lines)}")
    
    # 전역 범위 라인들 확인
    global_lines_nums = []
    for i in range(1, total_lines + 1):
        if i not in function_lines:
            global_lines_nums.append(i)
    
    if global_lines_nums:
        print(f"  📝 전역 라인들: {global_lines_nums}")
        print(f"  전역 라인 내용:")
        for line_num in global_lines_nums[:10]:  # 처음 10개만
            line_content = lines[line_num - 1] if line_num <= len(lines) else ""
            print(f"    라인 {line_num:2d}: {repr(line_content)}")
    else:
        print(f"  ⚠️ 전역 라인이 없음! 모든 라인이 함수 범위로 계산됨")
        
        # 함수 범위가 겹치는지 확인
        print(f"\n🔍 함수 범위 겹침 분석:")
        func_ranges = []
        for func in functions:
            if func['name'] != 'globals_and_imports':
                start = func['start_line']
                end = func['end_line']
                func_ranges.append((func['name'], start, end))
        
        # 범위 정렬
        func_ranges.sort(key=lambda x: x[1])
        
        for i, (name, start, end) in enumerate(func_ranges):
            print(f"    {i+1:2d}. {name:20} | {start:2d}-{end:2d}")
            
            # 이전 함수와 겹치는지 확인
            if i > 0:
                prev_name, prev_start, prev_end = func_ranges[i-1]
                if start <= prev_end:
                    overlap = min(end, prev_end) - start + 1
                    print(f"        ⚠️ {prev_name}와 {overlap}줄 겹침! ({start}-{min(end, prev_end)})")

async def debug_real_file():
    """실제 파일에서 globals 문제 디버깅"""
    print("\n📋 2. 실제 파일 디버깅 (code_analysis_service.py)")
    print("-" * 40)
    
    with open('app/services/code_analysis_service.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.splitlines()
    total_lines = len(lines)
    
    print(f"📊 파일 정보:")
    print(f"  총 라인 수: {total_lines}")
    print(f"  파일 크기: {len(content):,} 바이트")
    
    # 첫 20줄 확인 (임포트 등이 있을 것)
    print(f"\n📝 파일 시작 부분 (처음 10줄):")
    for i in range(min(10, len(lines))):
        line_content = lines[i]
        print(f"  라인 {i+1:2d}: {repr(line_content[:60])}")
    
    # 함수 추출
    functions = await extract_functions_by_type(content, 'code_analysis_service.py', {})
    
    # 함수 범위 수집 및 분석
    function_lines = set()
    print(f"\n📋 추출된 함수들 (처음 5개):")
    
    non_global_functions = [f for f in functions if f['name'] != 'globals_and_imports']
    for i, func in enumerate(non_global_functions[:5]):
        start = func['start_line']
        end = func['end_line']
        span = end - start + 1
        print(f"  {i+1}. {func['name']:30} | {start:3d}-{end:3d} ({span:3d}줄)")
        function_lines.update(range(start, end + 1))
    
    print(f"     ... 및 {len(non_global_functions) - 5}개 더")
    
    # 전체 함수 범위 계산
    for func in non_global_functions:
        start = func['start_line']
        end = func['end_line']
        function_lines.update(range(start, end + 1))
    
    print(f"\n📈 최종 범위 분석:")
    print(f"  총 라인 수: {total_lines}")
    print(f"  함수 범위 라인 수: {len(function_lines)}")
    print(f"  전역 범위 라인 수: {total_lines - len(function_lines)}")
    print(f"  커버리지: {len(function_lines)/total_lines*100:.1f}%")
    
    # 전역 라인들이 있는지 확인
    global_line_nums = []
    for i in range(1, total_lines + 1):
        if i not in function_lines:
            global_line_nums.append(i)
    
    if global_line_nums:
        print(f"\n📝 전역 라인들 (처음 10개): {global_line_nums[:10]}")
        for line_num in global_line_nums[:10]:
            line_content = lines[line_num - 1] if line_num <= len(lines) else ""
            print(f"  라인 {line_num:3d}: {repr(line_content[:50])}")
    else:
        print(f"\n⚠️ 문제 확인: 모든 라인이 함수 범위!")
        
        # 가장 큰 함수들 확인
        print(f"\n🔍 가장 큰 함수들:")
        large_functions = sorted(non_global_functions, 
                               key=lambda x: x['end_line'] - x['start_line'] + 1, 
                               reverse=True)[:3]
        
        for func in large_functions:
            start = func['start_line']
            end = func['end_line']
            span = end - start + 1
            print(f"  📋 {func['name']:30} | {start:3d}-{end:3d} ({span:3d}줄)")

if __name__ == "__main__":
    asyncio.run(debug_globals_issue())
    print()
    asyncio.run(debug_real_file()) 