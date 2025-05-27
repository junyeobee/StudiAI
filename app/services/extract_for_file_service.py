import ast
import re
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Type, Tuple
from app.utils.logger import api_logger


class BaseExtractor(ABC):
    """함수 추출기 베이스 클래스"""
    
    @abstractmethod
    async def extract_functions(self, content: str, filename: str, diff_info: Dict[int, Dict]) -> List[Dict[str, Any]]:
        """파일에서 함수들을 추출하는 추상 메서드"""
        pass
    
    def _get_language_patterns(self) -> Dict[str, Any]:
        """언어별 패턴 정의 (각 언어에서 오버라이드)"""
        return {
            'line_comments': ['//'],           # 라인 주석 패턴
            'block_comments': [('/*', '*/')], # 블록 주석 패턴 (시작, 끝)
            'doc_comments': ['/**'],           # 문서화 주석 패턴
            'decorators': ['@'],               # 데코레이터/어노테이션 패턴
            'stop_keywords': ['function', 'class', 'const', 'let', 'var']  # 중단 키워드들
        }
    
    def _extract_function_with_context(self, lines: List[str], func_start: int, func_end: int, func_name: str) -> Tuple[str, int]:
        """역방향 스캔으로 함수와 관련 컨텍스트(데코레이터, 주석, 독스트링) 추출"""
        patterns = self._get_language_patterns()
        
        # 1. 함수 시작점에서 위로 역방향 스캔
        actual_start = func_start
        empty_line_count = 0
        in_block_comment = False
        block_comment_start = None
        
        for i in range(func_start - 2, -1, -1):  # func_start-1부터 역순으로 (0-based)
            line = lines[i].strip()
            
            # 빈 줄 처리
            if not line:
                empty_line_count += 1
                if empty_line_count >= 2:  # 연속 빈 줄 2개면 중단
                    break
                continue
            else:
                empty_line_count = 0
            
            # 블록 주석 처리 (역방향이므로 끝부터 찾음)
            for block_start, block_end in patterns['block_comments']:
                if line.endswith(block_end) and not in_block_comment:
                    in_block_comment = True
                    block_comment_start = block_start
                    actual_start = i + 1  # 1-based로 변환
                    continue
                elif block_comment_start and line.startswith(block_comment_start) and in_block_comment:
                    in_block_comment = False
                    actual_start = i + 1  # 1-based로 변환
                    continue
            
            if in_block_comment:
                actual_start = i + 1  # 1-based로 변환
                continue
            
            # 포함할 것들 체크
            should_include = False
            
            # 데코레이터/어노테이션
            for decorator_pattern in patterns['decorators']:
                if decorator_pattern and line.startswith(decorator_pattern):
                    should_include = True
                    break
            
            # 라인 주석
            if not should_include:
                for comment_pattern in patterns['line_comments']:
                    if comment_pattern and line.startswith(comment_pattern):
                        should_include = True
                        break
            
            # 문서화 주석
            if not should_include:
                for doc_pattern in patterns['doc_comments']:
                    if doc_pattern and line.startswith(doc_pattern):
                        should_include = True
                        break
            
            if should_include:
                actual_start = i + 1  # 1-based로 변환
                continue
            
            # 중단 조건: 다른 정의들
            should_stop = False
            for keyword in patterns['stop_keywords']:
                if keyword and (line.startswith(keyword + ' ') or line.startswith(keyword + '\t')):
                    should_stop = True
                    break
            
            if should_stop:
                break
        
        # 2. 실제 시작점부터 함수 끝까지 코드 추출
        full_code = '\n'.join(lines[actual_start-1:func_end])
        
        api_logger.info(f"함수 '{func_name}' 컨텍스트 추출: {actual_start}~{func_end} 라인 ({func_end - actual_start + 1}줄)")
        
        return full_code, actual_start
    
    def _find_function_end_by_braces(self, content: str, start_pos: int) -> int:
        """중괄호 매칭으로 함수 끝 위치 찾기 (C계열 언어용)"""
        brace_count = 0
        i = start_pos
        found_first_brace = False
        
        while i < len(content):
            char = content[i]
            if char == '{':
                brace_count += 1
                found_first_brace = True
            elif char == '}':
                brace_count -= 1
                if found_first_brace and brace_count == 0:
                    return content[:i+1].count('\n') + 1
            i += 1
        
        return content[:start_pos].count('\n') + 10  # 기본값


class ExtractorRegistry:
    """추출기 레지스트리 - 데코레이터를 통한 자동 등록"""
    
    _extractors: Dict[str, Type[BaseExtractor]] = {}
    _instances: Dict[str, BaseExtractor] = {}  # 싱글톤 캐시
    
    @classmethod
    def register(cls, file_extensions: List[str]):
        """파일 확장자별 추출기 등록 데코레이터"""
        def decorator(extractor_class: Type[BaseExtractor]) -> Type[BaseExtractor]:
            for ext in file_extensions:
                cls._extractors[ext.lower()] = extractor_class
                api_logger.info(f"추출기 등록됨: {ext} -> {extractor_class.__name__}")
            return extractor_class
        return decorator
    
    @classmethod
    def get_extractor(cls, file_extension: str) -> BaseExtractor:
        """파일 확장자에 맞는 추출기 반환 (캐싱 적용)"""
        ext = file_extension.lower()
        
        # 캐시에서 먼저 확인
        if ext in cls._instances:
            return cls._instances[ext]
        
        # 등록된 추출기 클래스 찾기
        extractor_class = cls._extractors.get(ext)
        
        if extractor_class is None:
            api_logger.warning(f"지원하지 않는 파일 확장자: {ext}, GenericExtractor 사용")
            extractor_class = GenericExtractor
        
        # 인스턴스 생성 및 캐싱
        try:
            instance = extractor_class()
            cls._instances[ext] = instance
            api_logger.info(f"추출기 인스턴스 생성됨: {ext} -> {extractor_class.__name__}")
            return instance
        except Exception as e:
            api_logger.error(f"추출기 인스턴스 생성 실패: {extractor_class.__name__}, 오류: {e}")
            # Fallback으로 GenericExtractor 사용
            fallback_instance = GenericExtractor()
            cls._instances[ext] = fallback_instance
            return fallback_instance
    
    @classmethod
    def get_supported_extensions(cls) -> List[str]:
        """지원하는 파일 확장자 목록 반환"""
        return list(cls._extractors.keys())
    
    @classmethod
    def clear_cache(cls):
        """인스턴스 캐시 초기화 (테스트용)"""
        cls._instances.clear()


@ExtractorRegistry.register(['py'])
class PythonExtractor(BaseExtractor):
    """Python 파일 함수 추출기 (AST 사용)"""
    
    def _get_language_patterns(self) -> Dict[str, Any]:
        """Python 언어 패턴 정의"""
        return {
            'line_comments': ['#'],
            'block_comments': [('"""', '"""'), ("'''", "'''")],
            'doc_comments': ['"""', "'''"],
            'decorators': ['@'],
            'stop_keywords': ['def', 'async def', 'class', 'import', 'from']
        }
    
    async def extract_functions(self, content: str, filename: str, diff_info: Dict[int, Dict]) -> List[Dict[str, Any]]:
        """Python 파일에서 함수/메서드 개별 추출 (AST 사용)"""
        functions = []
        api_logger.info(f"Python 파일 파싱 시작: {filename}")
        
        try:
            tree = ast.parse(content)
            lines = content.splitlines()
            
            # 전역 임포트 및 상수 수집
            function_lines = set()
            
            for node in ast.walk(tree):
                # 클래스 정의 처리
                if isinstance(node, ast.ClassDef):
                    class_start = node.lineno
                    class_end = getattr(node, 'end_lineno', class_start)
                    
                    # 클래스 내 메서드들을 개별 함수로 처리
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            method_start = item.lineno
                            method_end = getattr(item, 'end_lineno', method_start)
                            
                            # 메서드 코드 추출 (컨텍스트 포함)
                            method_code, actual_start = self._extract_function_with_context(
                                lines, method_start, method_end, f"{node.name}.{item.name}"
                            )
                            
                            # 메서드 관련 변경 사항 찾기
                            method_changes = {
                                line_num: change for line_num, change in diff_info.items()
                                if actual_start <= line_num <= method_end
                            }
                            
                            function_name = f"{node.name}.{item.name}"  # 클래스.메서드 형식
                            
                            functions.append({
                                'name': function_name,
                                'type': 'method',
                                'code': method_code,
                                'start_line': actual_start,
                                'end_line': method_end,
                                'filename': filename,
                                'class_name': node.name,
                                'changes': method_changes,
                                'has_changes': bool(method_changes)
                            })
                            
                            # 함수 라인 기록 (컨텍스트 포함)
                            function_lines.update(range(actual_start, method_end + 1))
                
                # 독립 함수 처리
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # 클래스 내부가 아닌 독립 함수만
                    parent_classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
                    is_in_class = any(
                        class_node.lineno <= node.lineno <= getattr(class_node, 'end_lineno', class_node.lineno)
                        for class_node in parent_classes
                    )
                    
                    if not is_in_class:
                        func_start = node.lineno
                        func_end = getattr(node, 'end_lineno', func_start)
                        
                        # 독립 함수 코드 추출 (컨텍스트 포함)
                        func_code, actual_start = self._extract_function_with_context(
                            lines, func_start, func_end, node.name
                        )
                        
                        func_changes = {
                            line_num: change for line_num, change in diff_info.items()
                            if actual_start <= line_num <= func_end
                        }
                        
                        functions.append({
                            'name': node.name,
                            'type': 'function',
                            'code': func_code,
                            'start_line': actual_start,
                            'end_line': func_end,
                            'filename': filename,
                            'changes': func_changes,
                            'has_changes': bool(func_changes)
                        })
                        
                        function_lines.update(range(actual_start, func_end + 1))
            
            # 전역 코드 (임포트, 상수 등) 처리
            global_lines = []
            global_changes = {}
            
            for i, line in enumerate(lines, 1):
                if i not in function_lines:
                    global_lines.append(line)
                    if i in diff_info:
                        global_changes[i] = diff_info[i]
            
            if global_lines or global_changes:
                functions.insert(0, {
                    'name': 'globals_and_imports',
                    'type': 'global',
                    'code': '\n'.join(global_lines),
                    'start_line': 1,
                    'end_line': len(lines),
                    'filename': filename,
                    'changes': global_changes,
                    'has_changes': bool(global_changes)
                })
            
            api_logger.info(f"Python 파일 파싱 완료: {len(functions)}개 함수 추출")
            return functions
            
        except SyntaxError as e:
            api_logger.error(f"Python 파일 파싱 오류: {e}")
            # 파싱 실패 시 전체 파일을 하나의 함수로 처리
            return [{
                'name': 'entire_file',
                'type': 'file',
                'code': content,
                'start_line': 1,
                'end_line': len(content.splitlines()),
                'filename': filename,
                'changes': diff_info,
                'has_changes': bool(diff_info)
            }]


@ExtractorRegistry.register(['js', 'ts'])
class JavaScriptExtractor(BaseExtractor):
    """JavaScript/TypeScript 파일 함수 추출기"""
    
    def _get_language_patterns(self) -> Dict[str, Any]:
        """JavaScript/TypeScript 언어 패턴 정의"""
        return {
            'line_comments': ['//'],
            'block_comments': [('/*', '*/'), ('/**', '*/')],
            'doc_comments': ['/**'],
            'decorators': ['@'],  # TypeScript 데코레이터
            'stop_keywords': ['function', 'class', 'const', 'let', 'var', 'import', 'export']
        }
    
    async def extract_functions(self, content: str, filename: str, diff_info: Dict[int, Dict]) -> List[Dict[str, Any]]:
        """JavaScript/TypeScript 파일에서 함수 추출"""
        functions = []
        lines = content.splitlines()
        
        # JS/TS 함수 패턴들
        patterns = [
            r'(?:export\s+)?(?:async\s+)?function\s+(\w+)',  # function 선언
            r'(?:export\s+)?const\s+(\w+)\s*=.*?(?:async\s+)?(?:function|\(.*?\)\s*=>)',  # const 함수
            r'(?:export\s+)?let\s+(\w+)\s*=.*?(?:async\s+)?(?:function|\(.*?\)\s*=>)',  # let 함수
            r'(\w+)\s*:\s*(?:async\s+)?function',  # 객체 메서드
            r'(\w+)\s*\([^)]*\)\s*\{',  # 메서드 단축 문법
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                func_name = match.group(1)
                func_start_pos = match.start()
                
                # 함수 시작 라인 계산
                func_start_line = content[:func_start_pos].count('\n') + 1
                
                # 중괄호 매칭으로 함수 끝 찾기
                func_end_line = self._find_function_end_by_braces(content, func_start_pos)
                
                if func_end_line > func_start_line:
                    # 함수 코드 추출 (컨텍스트 포함)
                    func_code, actual_start = self._extract_function_with_context(
                        lines, func_start_line, func_end_line, func_name
                    )
                    
                    func_changes = {
                        line_num: change for line_num, change in diff_info.items()
                        if actual_start <= line_num <= func_end_line
                    }
                    
                    functions.append({
                        'name': func_name,
                        'type': 'function',
                        'code': func_code,
                        'start_line': actual_start,
                        'end_line': func_end_line,
                        'filename': filename,
                        'changes': func_changes,
                        'has_changes': bool(func_changes)
                    })
        
        # 함수가 없으면 전체 파일을 하나의 단위로 처리
        if not functions:
            functions.append({
                'name': 'entire_file',
                'type': 'file',
                'code': content,
                'start_line': 1,
                'end_line': len(lines),
                'filename': filename,
                'changes': diff_info,
                'has_changes': bool(diff_info)
            })
        
        api_logger.info(f"JavaScript/TypeScript 파일 파싱 완료: {len(functions)}개 함수 추출")
        return functions


@ExtractorRegistry.register(['java'])
class JavaExtractor(BaseExtractor):
    """Java 파일 함수 추출기"""
    
    def _get_language_patterns(self) -> Dict[str, Any]:
        """Java 언어 패턴 정의"""
        return {
            'line_comments': ['//'],
            'block_comments': [('/*', '*/'), ('/**', '*/')],
            'doc_comments': ['/**'],
            'decorators': ['@'],  # Java 어노테이션
            'stop_keywords': ['public', 'private', 'protected', 'class', 'interface', 'import', 'package']
        }
    
    async def extract_functions(self, content: str, filename: str, diff_info: Dict[int, Dict]) -> List[Dict[str, Any]]:
        """Java 파일에서 메서드 추출"""
        functions = []
        lines = content.splitlines()
        
        # Java 메서드 패턴
        pattern = r'(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?[\w<>\[\]]+\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{'
        
        for match in re.finditer(pattern, content, re.MULTILINE):
            method_name = match.group(1)
            method_start_pos = match.start()
            
            # 메서드 시작 라인 계산
            method_start_line = content[:method_start_pos].count('\n') + 1
            
            # 중괄호 매칭으로 메서드 끝 찾기
            method_end_line = self._find_function_end_by_braces(content, method_start_pos)
            
            if method_end_line > method_start_line:
                # 메서드 코드 추출 (컨텍스트 포함)
                method_code, actual_start = self._extract_function_with_context(
                    lines, method_start_line, method_end_line, method_name
                )
                
                method_changes = {
                    line_num: change for line_num, change in diff_info.items()
                    if actual_start <= line_num <= method_end_line
                }
                
                functions.append({
                    'name': method_name,
                    'type': 'method',
                    'code': method_code,
                    'start_line': actual_start,
                    'end_line': method_end_line,
                    'filename': filename,
                    'changes': method_changes,
                    'has_changes': bool(method_changes)
                })
        
        # 메서드가 없으면 전체 파일을 하나의 단위로 처리
        if not functions:
            functions.append({
                'name': 'entire_file',
                'type': 'file',
                'code': content,
                'start_line': 1,
                'end_line': len(lines),
                'filename': filename,
                'changes': diff_info,
                'has_changes': bool(diff_info)
            })
        
        api_logger.info(f"Java 파일 파싱 완료: {len(functions)}개 메서드 추출")
        return functions


@ExtractorRegistry.register(['c', 'cpp', 'cc', 'cxx'])
class CExtractor(BaseExtractor):
    """C/C++ 파일 함수 추출기"""
    
    def _get_language_patterns(self) -> Dict[str, Any]:
        """C/C++ 언어 패턴 정의"""
        return {
            'line_comments': ['//'],
            'block_comments': [('/*', '*/'), ('/**', '*/')],
            'doc_comments': ['/**'],
            'decorators': ['[['],  # C++11 attributes
            'stop_keywords': ['int', 'void', 'char', 'float', 'double', 'struct', 'class', 'typedef', '#include', '#define']
        }
    
    async def extract_functions(self, content: str, filename: str, diff_info: Dict[int, Dict]) -> List[Dict[str, Any]]:
        """C/C++ 파일에서 함수 추출"""
        functions = []
        lines = content.splitlines()
        
        # C/C++ 함수 패턴
        pattern = r'[\w\*\s:]+\s+(\w+)\s*\([^)]*\)\s*\{'
        
        for match in re.finditer(pattern, content, re.MULTILINE):
            func_name = match.group(1)
            func_start_pos = match.start()
            
            # 함수 시작 라인 계산
            func_start_line = content[:func_start_pos].count('\n') + 1
            
            # 중괄호 매칭으로 함수 끝 찾기
            func_end_line = self._find_function_end_by_braces(content, func_start_pos)
            
            if func_end_line > func_start_line:
                # 함수 코드 추출 (컨텍스트 포함)
                func_code, actual_start = self._extract_function_with_context(
                    lines, func_start_line, func_end_line, func_name
                )
                
                func_changes = {
                    line_num: change for line_num, change in diff_info.items()
                    if actual_start <= line_num <= func_end_line
                }
                
                functions.append({
                    'name': func_name,
                    'type': 'function',
                    'code': func_code,
                    'start_line': actual_start,
                    'end_line': func_end_line,
                    'filename': filename,
                    'changes': func_changes,
                    'has_changes': bool(func_changes)
                })
        
        # 함수가 없으면 전체 파일을 하나의 단위로 처리
        if not functions:
            functions.append({
                'name': 'entire_file',
                'type': 'file',
                'code': content,
                'start_line': 1,
                'end_line': len(lines),
                'filename': filename,
                'changes': diff_info,
                'has_changes': bool(diff_info)
            })
        
        api_logger.info(f"C/C++ 파일 파싱 완료: {len(functions)}개 함수 추출")
        return functions


class GenericExtractor(BaseExtractor):
    """일반 파일 추출기 (Fallback)"""
    
    async def extract_functions(self, content: str, filename: str, diff_info: Dict[int, Dict]) -> List[Dict[str, Any]]:
        """지원하지 않는 파일 타입의 경우 전체 파일을 하나의 단위로 처리"""
        api_logger.info(f"일반 파일로 처리: {filename}")
        
        return [{
            'name': 'entire_file',
            'type': 'file',
            'code': content,
            'start_line': 1,
            'end_line': len(content.splitlines()),
            'filename': filename,
            'changes': diff_info,
            'has_changes': bool(diff_info)
        }]


# 메인 함수
async def extract_functions_by_type(file_content: str, filename: str, diff_info: Dict[int, Dict]) -> List[Dict[str, Any]]:
    """파일 타입에 따라 적절한 추출기를 사용하여 함수들을 추출"""
    
    # 파일 확장자 추출
    if '.' not in filename:
        api_logger.warning(f"확장자가 없는 파일: {filename}, 일반 추출기 사용")
        ext = 'generic'
    else:
        ext = filename.split('.')[-1].lower()
    
    try:
        # 레지스트리에서 적절한 추출기 가져오기
        extractor = ExtractorRegistry.get_extractor(ext)
        
        # 함수 추출 실행
        api_logger.info(f"파일 '{filename}' ({ext}) 함수 추출 시작")
        functions = await extractor.extract_functions(file_content, filename, diff_info)
        
        api_logger.info(f"파일 '{filename}' 함수 추출 완료: {len(functions)}개 함수")
        return functions
        
    except Exception as e:
        api_logger.error(f"파일 '{filename}' 함수 추출 실패: {str(e)}")
        
        # 에러 발생 시 Fallback으로 GenericExtractor 사용
        try:
            fallback_extractor = GenericExtractor()
            return await fallback_extractor.extract_functions(file_content, filename, diff_info)
        except Exception as fallback_error:
            api_logger.error(f"Fallback 추출기도 실패: {str(fallback_error)}")
            
            # 최후의 수단: 빈 결과 반환
            return [{
                'name': 'error_file',
                'type': 'error',
                'code': file_content,
                'start_line': 1,
                'end_line': len(file_content.splitlines()),
                'filename': filename,
                'changes': diff_info,
                'has_changes': bool(diff_info),
                'error': str(e)
            }]


# 유틸리티 함수들
def get_supported_file_types() -> List[str]:
    """지원하는 파일 타입 목록 반환"""
    return ExtractorRegistry.get_supported_extensions()


def is_supported_file_type(filename: str) -> bool:
    """파일이 지원되는 타입인지 확인"""
    if '.' not in filename:
        return False
    
    ext = filename.split('.')[-1].lower()
    return ext in ExtractorRegistry.get_supported_extensions()