import asyncio
import logging
import sys
from pathlib import Path

# 프로젝트 루트 디렉터리를 Python 경로에 추가
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent  # tests/debug/ -> tests/ -> 루트
sys.path.insert(0, str(project_root))

from app.services.extract_for_file_service import extract_functions_by_type

async def test_specific_issues():
    """발견된 특정 문제들 상세 분석"""
    
    print("🔍 특정 문제 케이스 분석")
    print("=" * 60)
    
    # 1. 빈 globals_and_imports 문제 분석
    await test_empty_globals_issue()
    
    # 2. 복잡한 클래스 파싱 문제 분석
    await test_complex_class_parsing()

async def test_empty_globals_issue():
    """빈 globals_and_imports 문제 분석"""
    print("📋 1. 빈 globals_and_imports 문제 분석")
    print("-" * 40)
    
    # code_analysis_service.py에서 빈 globals_and_imports 확인
    with open('app/services/code_analysis_service.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    functions = await extract_functions_by_type(content, 'code_analysis_service.py', {})
    
    globals_func = next((f for f in functions if f['name'] == 'globals_and_imports'), None)
    if globals_func:
        print(f"📊 globals_and_imports 상태:")
        print(f"  - 범위: {globals_func['start_line']}-{globals_func['end_line']} 라인")
        print(f"  - 코드 길이: {len(globals_func['code'])} 문자")
        print(f"  - 빈 코드 여부: {not globals_func['code'].strip()}")
        
        if not globals_func['code'].strip():
            print("  ⚠️ 확인: globals_and_imports가 비어있음!")
            
            # 전체 파일에서 함수가 아닌 부분 확인
            lines = content.splitlines()
            total_lines = len(lines)
            
            # 모든 함수 범위 수집
            function_lines = set()
            for func in functions:
                if func['name'] != 'globals_and_imports':
                    start = func['start_line']
                    end = func['end_line'] 
                    function_lines.update(range(start, end + 1))
            
            # 전역 범위 라인들 확인
            global_lines = []
            for i in range(1, total_lines + 1):
                if i not in function_lines:
                    global_lines.append(i)
            
            print(f"  📈 총 라인 수: {total_lines}")
            print(f"  🔧 함수 범위 라인 수: {len(function_lines)}")
            print(f"  🌐 전역 범위 라인 수: {len(global_lines)}")
            
            if global_lines:
                print(f"  📝 전역 라인 샘플 (처음 5개): {global_lines[:5]}")
                for line_num in global_lines[:5]:
                    line_content = lines[line_num - 1] if line_num <= len(lines) else ""
                    print(f"    라인 {line_num}: {repr(line_content[:50])}")

async def test_complex_class_parsing():
    """복잡한 클래스 파싱 문제 분석"""
    print("\n📋 2. 복잡한 클래스 파싱 분석")
    print("-" * 40)
    
    # 복잡한 클래스 테스트 케이스
    complex_class_content = '''
@decorator_one
@decorator_two(param="value")  
@decorator_three
class ComplexService(BaseService[Dict[str, any]]):
    """다중 데코레이터를 가진 복잡한 서비스"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        # 중첩 함수 정의
        def inner_validator(item):
            return isinstance(item, dict)
        
        self._validator = inner_validator
    
    @async_retry(max_retries=3, delay=1.0)
    @log_execution_time
    @validate_params
    async def complex_async_method(self, data: List[Dict]) -> Dict:
        """매우 복잡한 비동기 메서드"""
        try:
            results = {}
            
            async def process_batch(batch: List[Dict]) -> List[any]:
                tasks = []
                for item in batch:
                    # 람다 함수 사용
                    processor = lambda x: self._transform_item(x)
                    task = asyncio.create_task(self._async_process_item(processor(item)))
                    tasks.append(task)
                
                return await asyncio.gather(*tasks, return_exceptions=True)
            
            return results
            
        except Exception as e:
            self.logger.error(f"복잡한 메서드 실행 실패: {e}")
            raise ComplexServiceError(f"처리 실패: {str(e)}") from e
        finally:
            await self._cleanup_resources()
    
    async def _async_process_item(self, item: Dict) -> any:
        """내부 비동기 헬퍼 메서드"""
        await asyncio.sleep(0.1)
        return item
    
    def _transform_item(self, item: Dict) -> Dict:
        """아이템 변환 헬퍼"""
        return {**item, 'processed': True}
    
    async def _cleanup_resources(self):
        """리소스 정리"""
        pass
'''
    
    functions = await extract_functions_by_type(complex_class_content, 'complex_class_test.py', {})
    
    print(f"📊 복잡한 클래스 파싱 결과:")
    print(f"  총 함수: {len(functions)}개")
    
    # 상세 분석
    class_functions = []
    method_functions = []
    other_functions = []
    
    for func in functions:
        func_type = func.get('type', 'unknown')
        name = func.get('name', 'unknown')
        
        if func_type in ['class', 'class_header']:
            class_functions.append(func)
        elif func_type == 'method':
            method_functions.append(func)
        else:
            other_functions.append(func)
        
        print(f"  📋 {name:30} | {func_type:12} | {func['start_line']:3d}-{func['end_line']:3d}")
        
        # ComplexService 관련 분석
        if 'ComplexService' in name:
            print(f"    🎯 ComplexService 감지!")
            code_preview = func.get('code', '')[:100].replace('\n', ' ')
            print(f"    📝 코드 미리보기: {code_preview}...")
    
    print(f"\n📈 분류 결과:")
    print(f"  🏛️ 클래스: {len(class_functions)}개")
    print(f"  📝 메서드: {len(method_functions)}개") 
    print(f"  🔧 기타: {len(other_functions)}개")
    
    # 예상 vs 실제 비교
    expected_methods = ['__init__', 'complex_async_method', '_async_process_item', '_transform_item', '_cleanup_resources']
    found_methods = [f['name'].split('.')[-1] for f in method_functions if '.' in f['name']]
    
    print(f"\n🔍 메서드 감지 분석:")
    print(f"  예상 메서드: {expected_methods}")
    print(f"  감지된 메서드: {found_methods}")
    
    missing_methods = set(expected_methods) - set(found_methods)
    if missing_methods:
        print(f"  ⚠️ 누락된 메서드: {list(missing_methods)}")
    
    extra_methods = set(found_methods) - set(expected_methods)
    if extra_methods:
        print(f"  ➕ 추가 감지된 메서드: {list(extra_methods)}")

if __name__ == "__main__":
    asyncio.run(test_specific_issues()) 