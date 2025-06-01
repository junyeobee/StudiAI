"""
extract_for_file_service.py 함수 추출 로직 테스트
"""
import pytest
import os
from app.services.extract_for_file_service import extract_functions_by_type

# 테스트 케이스 정의
TEST_CASES = [
    # Python 테스트 케이스들
    (
        "PY_BASIC_01",
        "py", 
        "tests/snippets/python/simple_functions.py",
        ["globals_and_imports", "foo", "bar", "process_list"]
    ),
    (
        "PY_DECORATOR_01", 
        "py",
        "tests/snippets/python/decorator_functions.py", 
        ["globals_and_imports", "my_decorator", "list_learning_pages", "create_pages", "Baz.qux", "Baz.static_method"]
    ),
    (
        "PY_ASYNC_01",
        "py",
        "tests/snippets/python/async_functions.py",
        ["globals_and_imports", "fetch_data", "process_data", "process_item", "sync_helper"]
    ),
    
    # JavaScript 테스트 케이스들
    (
        "JS_BASIC_01",
        "js",
        "tests/snippets/javascript/basic_functions.js", 
        ["globals_and_imports", "foo", "bar", "processArray", "fetchUserData"]
    ),
    (
        "JS_ARROW_01",
        "js", 
        "tests/snippets/javascript/arrow_functions.js",
        ["globals_and_imports", "simpleArrow", "addNumbers", "asyncArrow", "nestedArrow", "regularFunction"]
    ),
]

class TestExtractForFileService:
    """함수 추출 서비스 테스트 클래스"""
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_id, ext, filepath, expected_functions", TEST_CASES)
    async def test_extract_functions(self, test_id, ext, filepath, expected_functions):
        """함수 추출 정확성 테스트"""
        # 파일 존재 확인
        assert os.path.exists(filepath), f"테스트 파일이 존재하지 않습니다: {filepath}"
        
        # 파일 내용 읽기
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 함수 추출 실행 (빈 diff_info로 테스트)
        functions = await extract_functions_by_type(content, f"test.{ext}", {})
        
        # 추출된 함수 이름들
        extracted_names = [func['name'] for func in functions]
        
        print(f"\n=== {test_id} 테스트 결과 ===")
        print(f"기대값: {expected_functions}")
        print(f"실제값: {extracted_names}")
        print(f"파일: {filepath}")
        
        # 기대하는 모든 함수가 추출되었는지 확인
        missing_functions = set(expected_functions) - set(extracted_names)
        extra_functions = set(extracted_names) - set(expected_functions)
        
        assert not missing_functions, f"{test_id}: 누락된 함수들: {missing_functions}"
        
        # 추가 함수가 있어도 경고만 출력 (너무 엄격하지 않게)
        if extra_functions:
            print(f"⚠️  예상보다 추가로 추출된 함수들: {extra_functions}")
        
        # globals_and_imports가 항상 첫 번째인지 확인
        if extracted_names and "globals_and_imports" in extracted_names:
            assert extracted_names[0] == "globals_and_imports", f"{test_id}: globals_and_imports가 첫 번째가 아님"
    
    @pytest.mark.asyncio
    async def test_unsupported_file_type(self):
        """지원하지 않는 파일 타입 테스트"""
        content = "This is a text file"
        functions = await extract_functions_by_type(content, "test.txt", {})
        
        # GenericExtractor가 사용되어 entire_file로 추출되어야 함
        assert len(functions) == 1
        assert functions[0]['name'] == 'entire_file'
        assert functions[0]['type'] == 'file'
    
    @pytest.mark.asyncio
    async def test_empty_file(self):
        """빈 파일 테스트"""
        content = ""
        functions = await extract_functions_by_type(content, "test.py", {})
        
        # 빈 파일도 globals_and_imports는 있어야 함
        assert len(functions) >= 1
        if functions:
            assert functions[0]['name'] == 'globals_and_imports'
    
    @pytest.mark.asyncio
    async def test_diff_info_integration(self):
        """diff_info와의 통합 테스트"""
        content = """
def test_func():
    return True

def another_func():
    return False
"""
        # 2번째 라인이 변경되었다고 가정
        diff_info = {2: {'type': 'modified', 'content': 'def test_func():'}}
        
        functions = await extract_functions_by_type(content, "test.py", diff_info)
        
        # 변경된 함수를 찾아서 has_changes가 True인지 확인
        test_func = next((f for f in functions if f['name'] == 'test_func'), None)
        assert test_func is not None
        assert test_func['has_changes'] == True
        
        # 변경되지 않은 함수는 has_changes가 False인지 확인
        another_func = next((f for f in functions if f['name'] == 'another_func'), None)
        assert another_func is not None
        assert another_func['has_changes'] == False

if __name__ == "__main__":
    # 개발 중 직접 실행을 위한 코드
    import asyncio
    
    async def run_single_test():
        test_instance = TestExtractForFileService()
        await test_instance.test_extract_functions("PY_BASIC_01", "py", "tests/snippets/python/simple_functions.py", ["globals_and_imports", "foo", "bar", "process_list"])
        print("단일 테스트 완료!")
    
    asyncio.run(run_single_test()) 