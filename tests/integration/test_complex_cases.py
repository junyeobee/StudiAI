import asyncio
import logging
import sys
from pathlib import Path

# 프로젝트 루트 디렉터리를 Python 경로에 추가
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent  # tests/integration/ -> tests/ -> 루트
sys.path.insert(0, str(project_root))

from app.services.extract_for_file_service import extract_functions_by_type, ExtractorRegistry

# 로그 레벨을 DEBUG로 설정
logging.getLogger('api').setLevel(logging.INFO)

async def test_complex_function_cases():
    """복잡한 함수 케이스들 테스트"""
    
    print("🧪 복잡한 함수 케이스 테스트 시작")
    print("=" * 80)
    
    # 테스트할 파일들 목록
    test_files = [
        'app/services/notion_service.py',
        'app/services/code_analysis_service.py', 
        'app/services/supa.py',
        'app/services/auth_service.py'
    ]
    
    for file_path in test_files:
        await test_file_complexity(file_path)
        print()

async def test_file_complexity(file_path: str):
    """개별 파일의 복잡성 테스트"""
    try:
        # 파일 읽기
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"📁 파일: {file_path}")
        print(f"📏 크기: {len(content):,} 바이트")
        print(f"📄 라인: {len(content.splitlines()):,} 줄")
        
        # 함수 추출
        filename = Path(file_path).name
        functions = await extract_functions_by_type(content, filename, {})
        
        # 통계 분석
        stats = analyze_function_complexity(functions)
        
        print(f"🔍 추출 결과:")
        print(f"  📊 총 함수: {stats['total']}개")
        print(f"  🏛️ 클래스: {stats['classes']}개")
        print(f"  🔧 함수: {stats['functions']}개") 
        print(f"  📝 메서드: {stats['methods']}개")
        print(f"  🌐 전역: {stats['globals']}개")
        
        # 복잡한 케이스들 상세 분석
        complex_cases = find_complex_cases(functions)
        if complex_cases:
            print(f"  🧩 복잡한 케이스: {len(complex_cases)}개")
            
            # 가장 흥미로운 케이스 몇 개만 표시
            for i, case in enumerate(complex_cases[:3], 1):
                print(f"    {i}. {case['name']} ({case['reason']}) | {case['start_line']}-{case['end_line']} 라인")
                
                # 첫 줄과 마지막 줄 미리보기
                first_line = case['code'].split('\n')[0].strip()
                if len(first_line) > 60:
                    first_line = first_line[:60] + "..."
                print(f"       📝 시작: {first_line}")
                
                if len(complex_cases) > 3 and i == 3:
                    print(f"       ... 및 {len(complex_cases) - 3}개 더")
        
        # 문제 케이스 확인
        problems = find_problematic_cases(functions)
        if problems:
            print(f"  ⚠️ 문제 케이스: {len(problems)}개")
            for problem in problems:
                print(f"    - {problem}")
                
    except Exception as e:
        print(f"❌ 파일 '{file_path}' 테스트 실패: {str(e)}")

def analyze_function_complexity(functions):
    """함수 복잡성 통계 분석"""
    stats = {
        'total': len(functions),
        'classes': 0,
        'functions': 0,
        'methods': 0,
        'globals': 0,
        'other': 0
    }
    
    for func in functions:
        func_type = func.get('type', 'unknown')
        if func_type in ['class', 'class_header']:
            stats['classes'] += 1
        elif func_type == 'function':
            stats['functions'] += 1
        elif func_type == 'method':
            stats['methods'] += 1
        elif func_type == 'global':
            stats['globals'] += 1
        else:
            stats['other'] += 1
    
    return stats

def find_complex_cases(functions):
    """복잡한 함수 케이스들 찾기"""
    complex_cases = []
    
    for func in functions:
        complexity_reasons = []
        code = func.get('code', '')
        name = func.get('name', 'unknown')
        
        # 복잡성 지표들
        if '@' in code and code.count('@') > 1:
            complexity_reasons.append('다중 데코레이터')
        
        if 'async' in code and 'await' in code:
            complexity_reasons.append('비동기 함수')
        
        if code.count('def ') > 1 or code.count('async def') > 1:
            complexity_reasons.append('중첩 함수')
        
        if any(pattern in code for pattern in ['@classmethod', '@staticmethod', '@property']):
            complexity_reasons.append('특수 메서드')
        
        if 'typing.' in code or any(generic in code for generic in ['List[', 'Dict[', 'Optional[', 'Union[']):
            complexity_reasons.append('타입 힌트')
        
        if code.count('try:') > 0:
            complexity_reasons.append('예외 처리')
        
        if len(code.splitlines()) > 50:
            complexity_reasons.append('긴 함수')
        
        if 'lambda' in code:
            complexity_reasons.append('람다 함수')
        
        if complexity_reasons:
            complex_cases.append({
                'name': name,
                'reason': ', '.join(complexity_reasons),
                'code': code,
                'start_line': func.get('start_line'),
                'end_line': func.get('end_line'),
                'complexity_score': len(complexity_reasons)
            })
    
    # 복잡성 점수로 정렬
    complex_cases.sort(key=lambda x: x['complexity_score'], reverse=True)
    return complex_cases

def find_problematic_cases(functions):
    """문제가 있을 수 있는 케이스들 찾기"""
    problems = []
    
    function_names = [f.get('name', '') for f in functions]
    
    # 중복 함수명 확인
    name_counts = {}
    for name in function_names:
        if name and name != 'globals_and_imports':
            name_counts[name] = name_counts.get(name, 0) + 1
    
    duplicates = [name for name, count in name_counts.items() if count > 1]
    if duplicates:
        problems.append(f"중복 함수명: {duplicates}")
    
    # 빈 함수 확인
    empty_functions = [f.get('name') for f in functions if not f.get('code', '').strip()]
    if empty_functions:
        problems.append(f"빈 함수: {empty_functions}")
    
    # 범위 이상 확인
    range_issues = []
    for func in functions:
        start = func.get('start_line', 0)
        end = func.get('end_line', 0)
        if start > end:
            range_issues.append(func.get('name'))
    
    if range_issues:
        problems.append(f"범위 오류: {range_issues}")
    
    return problems

async def test_custom_complex_file():
    """커스텀 복잡한 테스트 파일 생성 및 테스트"""
    print("🧪 커스텀 복잡한 케이스 테스트")
    print("=" * 50)
    
    # 복잡한 테스트 케이스가 포함된 파일 생성
    complex_test_content = '''"""
복잡한 함수 패턴들을 테스트하기 위한 파일
"""
import asyncio
from typing import List, Dict, Optional, Union, Generic, TypeVar
from dataclasses import dataclass
from abc import ABC, abstractmethod

T = TypeVar('T')

@dataclass
class ComplexDataClass:
    """복잡한 데이터클래스"""
    value: Optional[Union[str, int]]
    items: List[Dict[str, any]]

class BaseService(ABC, Generic[T]):
    """제네릭 베이스 서비스"""
    
    @abstractmethod
    async def process(self, item: T) -> Optional[T]:
        pass
    
    @classmethod
    def create_instance(cls) -> 'BaseService[T]':
        return cls()
    
    @staticmethod
    def validate_input(data: Dict[str, any]) -> bool:
        return all(key in data for key in ['id', 'name'])
    
    @property
    def service_name(self) -> str:
        return self.__class__.__name__

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
    async def complex_async_method(
        self, 
        data: List[Dict[str, Union[str, int]]], 
        options: Optional[Dict[str, any]] = None,
        callback: Optional[callable] = None
    ) -> Dict[str, List[Union[str, int]]]:
        """
        매우 복잡한 비동기 메서드
        - 다중 데코레이터
        - 복잡한 타입 힌트
        - 옵셔널 파라미터
        - 콜백 함수
        """
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
            
            # 중첩된 try-catch
            for batch in self._create_batches(data):
                try:
                    batch_results = await process_batch(batch)
                    results.update(batch_results)
                except Exception as batch_error:
                    self.logger.error(f"배치 처리 실패: {batch_error}")
                    continue
            
            if callback:
                await callback(results)
            
            return results
            
        except Exception as e:
            self.logger.error(f"복잡한 메서드 실행 실패: {e}")
            raise ComplexServiceError(f"처리 실패: {str(e)}") from e
        finally:
            await self._cleanup_resources()
    
    async def _async_process_item(self, item: Dict) -> any:
        """내부 비동기 헬퍼 메서드"""
        await asyncio.sleep(0.1)  # 시뮬레이션
        return item
    
    def _transform_item(self, item: Dict) -> Dict:
        """아이템 변환 헬퍼"""
        return {**item, 'processed': True}
    
    def _create_batches(self, data: List) -> List[List]:
        """배치 생성 헬퍼"""
        batch_size = 10
        return [data[i:i + batch_size] for i in range(0, len(data), batch_size)]
    
    async def _cleanup_resources(self):
        """리소스 정리"""
        pass

class ComplexServiceError(Exception):
    """커스텀 예외"""
    pass

# 전역 함수들
def decorator_one(cls):
    return cls

def decorator_two(param=None):
    def wrapper(cls):
        cls._param = param
        return cls
    return wrapper

def decorator_three(cls):
    cls._decorated = True
    return cls

async def complex_global_function(
    items: List[ComplexDataClass],
    processor: BaseService[any],
    *args,
    **kwargs
) -> Optional[List[any]]:
    """복잡한 전역 비동기 함수"""
    async with processor as service:
        results = []
        for item in items:
            result = await service.process(item.value)
            if result:
                results.append(result)
        return results if results else None
'''
    
    # 테스트 파일로 저장
    test_file_path = 'test_complex_patterns.py'
    with open(test_file_path, 'w', encoding='utf-8') as f:
        f.write(complex_test_content)
    
    # 함수 추출 테스트
    functions = await extract_functions_by_type(complex_test_content, test_file_path, {})
    
    print(f"📊 커스텀 테스트 결과:")
    print(f"  총 함수: {len(functions)}개")
    
    # 상세 분석
    for i, func in enumerate(functions, 1):
        print(f"{i:2d}. {func['name']:30} | {func['type']:10} | {func['start_line']:3d}-{func['end_line']:3d} 라인")
        
        # 특별히 복잡한 케이스들 하이라이트
        code = func.get('code', '')
        if '@' in code and 'async' in code and len(code.splitlines()) > 20:
            print(f"    🌟 매우 복잡한 케이스 감지!")
            first_line = code.split('\n')[0].strip()
            if len(first_line) > 50:
                first_line = first_line[:50] + "..."
            print(f"    📝 {first_line}")
    
    # 정리
    import os
    os.remove(test_file_path)

if __name__ == "__main__":
    asyncio.run(test_complex_function_cases())
    print()
    asyncio.run(test_custom_complex_file()) 