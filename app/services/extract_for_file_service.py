import ast
import re
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Type, Tuple
from app.utils.logger import api_logger

# Tree-sitter 관련 imports
try:
    import tree_sitter
    from tree_sitter import Language, Parser, Node
    import tree_sitter_python
    import tree_sitter_javascript
    import tree_sitter_java
    import tree_sitter_cpp
    TREE_SITTER_AVAILABLE = True
except ImportError as e:
    api_logger.warning(f"tree-sitter 라이브러리를 가져오지 못했습니다: {e}")
    TREE_SITTER_AVAILABLE = False


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
    
    def _is_block_comment_line(self, line: str, patterns: Dict[str, Any], comment_state: Dict) -> bool:
        """블록 주석 라인인지 확인하고 상태를 업데이트"""
        for block_start, block_end in patterns['block_comments']:
            # 블록 주석 끝 발견
            if line.endswith(block_end) and not comment_state['in_block']:
                comment_state['in_block'] = True
                comment_state['block_start'] = block_start
                return True
            # 블록 주석 시작 발견
            elif (comment_state['block_start'] and 
                  line.startswith(comment_state['block_start']) and 
                  comment_state['in_block']):
                comment_state['in_block'] = False
                return True
        
        return comment_state['in_block']
    
    def _should_include_line(self, line: str, patterns: Dict[str, Any]) -> bool:
        """라인이 포함되어야 하는지 판단 (데코레이터, 주석 등)"""
        # 데코레이터/어노테이션
        for decorator_pattern in patterns['decorators']:
            if decorator_pattern and line.startswith(decorator_pattern):
                return True
        
        # 라인 주석
        for comment_pattern in patterns['line_comments']:
            if comment_pattern and line.startswith(comment_pattern):
                return True
        
        # 문서화 주석
        for doc_pattern in patterns['doc_comments']:
            if doc_pattern and line.startswith(doc_pattern):
                return True
        
        return False
    
    def _should_stop_scanning(self, line: str, patterns: Dict[str, Any]) -> bool:
        """역방향 스캔을 중단해야 하는지 판단"""
        for keyword in patterns['stop_keywords']:
            if keyword and (line.startswith(keyword + ' ') or line.startswith(keyword + '\t')):
                return True
        return False
    
    def _extract_function_with_context(self, lines: List[str], func_start: int, func_end: int, func_name: str) -> Tuple[str, int]:
        """역방향 스캔으로 함수와 관련 컨텍스트(데코레이터, 주석, 독스트링) 추출"""
        patterns = self._get_language_patterns()
        
        # 1. 함수 시작점에서 위로 역방향 스캔
        actual_start = func_start
        empty_line_count = 0
        comment_state = {'in_block': False, 'block_start': None}
        
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
            
            # 블록 주석 처리
            if self._is_block_comment_line(line, patterns, comment_state):
                actual_start = i + 1  # 1-based로 변환
                continue
            
            if comment_state['in_block']:
                actual_start = i + 1  # 1-based로 변환
                continue
            
            # 포함할 것들 체크
            should_include = self._should_include_line(line, patterns)
            
            if should_include:
                actual_start = i + 1  # 1-based로 변환
                continue
            
            # 중단 조건: 다른 정의들
            should_stop = self._should_stop_scanning(line, patterns)
            
            if should_stop:
                break
        
        # 2. 실제 시작점부터 함수 끝까지 코드 추출
        full_code = '\n'.join(lines[actual_start-1:func_end])
        
        api_logger.debug(f"함수 '{func_name}' 컨텍스트 추출: {actual_start}~{func_end} 라인 ({func_end - actual_start + 1}줄)")
        
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


class TreeSitterBaseExtractor(BaseExtractor):
    """Tree-sitter 기반 추출기 베이스 클래스"""
    
    def __init__(self):
        if not TREE_SITTER_AVAILABLE:
            raise ImportError("tree-sitter가 설치되지 않았습니다")
        
        self.parser = Parser()
        self.language = self._get_language()
        if self.language:
            self.parser.set_language(self.language)
    
    @abstractmethod
    def _get_language(self) -> Optional[Language]:
        """각 언어별 tree-sitter Language 객체 반환"""
        pass
    
    @abstractmethod
    def _get_function_query(self) -> str:
        """함수/메서드를 찾는 tree-sitter 쿼리 반환"""
        pass
    
    def _parse_code(self, content: str) -> Optional[Node]:
        """코드를 파싱하여 AST 노드 반환"""
        try:
            tree = self.parser.parse(bytes(content, 'utf8'))
            return tree.root_node
        except Exception as e:
            api_logger.error(f"tree-sitter 파싱 실패: {e}")
            return None
    
    def _get_node_text(self, node: Node, content: bytes) -> str:
        """노드의 텍스트 내용 반환"""
        return content[node.start_byte:node.end_byte].decode('utf8')
    
    def _get_node_line_range(self, node: Node) -> Tuple[int, int]:
        """노드의 라인 범위 반환 (1-based)"""
        return node.start_point[0] + 1, node.end_point[0] + 1
    
    def _extract_function_name(self, node: Node, content: bytes) -> str:
        """함수 노드에서 함수명 추출"""
        # 기본 구현: identifier 노드 찾기
        for child in node.children:
            if child.type == 'identifier':
                return self._get_node_text(child, content)
        return "unknown_function"
    
    def _find_functions_with_query(self, root_node: Node, content: bytes) -> List[Dict[str, Any]]:
        """쿼리를 사용하여 함수들 찾기"""
        functions = []
        
        # 간단한 재귀 탐색으로 함수 노드들 찾기
        def visit_node(node: Node):
            if self._is_function_node(node):
                func_name = self._extract_function_name(node, content)
                start_line, end_line = self._get_node_line_range(node)
                
                # 함수 전체 텍스트 추출
                func_text = self._get_node_text(node, content)
                
                functions.append({
                    'name': func_name,
                    'node': node,
                    'start_line': start_line,
                    'end_line': end_line,
                    'text': func_text
                })
            
            for child in node.children:
                visit_node(child)
        
        visit_node(root_node)
        return functions
    
    def _is_function_node(self, node: Node) -> bool:
        """노드가 함수 정의인지 확인"""
        # 각 언어별로 오버라이드 필요
        function_types = ['function_definition', 'method_definition', 'function_declaration', 'arrow_function']
        return node.type in function_types
    
    async def extract_functions(self, content: str, filename: str, diff_info: Dict[int, Dict]) -> List[Dict[str, Any]]:
        """tree-sitter를 사용한 함수 추출"""
        api_logger.info(f"tree-sitter로 파일 파싱 시작: {filename}")
        
        # 코드 파싱
        root_node = self._parse_code(content)
        if not root_node:
            api_logger.error(f"파싱 실패, 정규식 방식으로 fallback: {filename}")
            return await self._fallback_extract(content, filename, diff_info)
        
        content_bytes = content.encode('utf8')
        lines = content.splitlines()
        
        # 함수들 찾기
        found_functions = self._find_functions_with_query(root_node, content_bytes)
        
        functions = []
        function_lines = set()
        
        for func_info in found_functions:
            func_start = func_info['start_line']
            func_end = func_info['end_line']
            func_name = func_info['name']
            
            # 컨텍스트 포함해서 추출
            func_code, actual_start = self._extract_function_with_context(
                lines, func_start, func_end, func_name
            )
            
            # 변경 사항 찾기
            func_changes = {
                line_num: change for line_num, change in diff_info.items()
                if actual_start <= line_num <= func_end
            }
            
            functions.append({
                'name': func_name,
                'type': self._determine_function_type(func_info['node']),
                'code': func_code,
                'start_line': actual_start,
                'end_line': func_end,
                'filename': filename,
                'changes': func_changes,
                'has_changes': bool(func_changes)
            })
            
            function_lines.update(range(actual_start, func_end + 1))
        
        # 전역 코드 처리
        self._add_global_code(functions, lines, diff_info, function_lines, filename)
        
        api_logger.info(f"tree-sitter 파싱 완료: {len(functions)}개 함수 추출")
        return functions
    
    def _determine_function_type(self, node: Node) -> str:
        """노드 타입에 따라 함수 타입 결정"""
        type_mapping = {
            'function_definition': 'function',
            'method_definition': 'method',
            'function_declaration': 'function',
            'arrow_function': 'function',
            'class_definition': 'class'
        }
        return type_mapping.get(node.type, 'function')
    
    def _add_global_code(self, functions: List[Dict], lines: List[str], diff_info: Dict, function_lines: set, filename: str):
        """전역 코드 (임포트, 상수 등) 추가"""
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
    
    async def _fallback_extract(self, content: str, filename: str, diff_info: Dict[int, Dict]) -> List[Dict[str, Any]]:
        """파싱 실패 시 fallback (전체 파일 처리)"""
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


class ExtractorRegistry:
    """추출기 레지스트리 - 데코레이터를 통한 자동 등록"""
    
    _extractors: Dict[str, Type[BaseExtractor]] = {}
    _instances: Dict[str, BaseExtractor] = {}  # 싱글톤 캐시
    _instance_creation_attempts: Dict[str, int] = {}  # 재시도 카운터
    
    @classmethod
    def register(cls, file_extensions: List[str]):
        """파일 확장자별 추출기 등록 데코레이터"""
        def decorator(extractor_class: Type[BaseExtractor]) -> Type[BaseExtractor]:
            for ext in file_extensions:
                ext_lower = ext.lower()
                cls._extractors[ext_lower] = extractor_class
                # 기존 캐시된 인스턴스 무효화
                if ext_lower in cls._instances:
                    api_logger.debug(f"추출기 재등록으로 캐시 무효화: {ext}")
                    del cls._instances[ext_lower]
                    cls._instance_creation_attempts.pop(ext_lower, None)
                api_logger.debug(f"추출기 등록됨: {ext} -> {extractor_class.__name__}")
            return extractor_class
        return decorator
    
    @classmethod
    def get_extractor(cls, file_extension: str) -> BaseExtractor:
        """파일 확장자에 맞는 추출기 반환 (캐싱 적용, 재시도 로직 포함)"""
        ext = file_extension.lower()
        
        # 캐시에서 먼저 확인
        if ext in cls._instances:
            return cls._instances[ext]
        
        # 재시도 횟수 확인 (무한 루프 방지)
        max_attempts = 3
        current_attempts = cls._instance_creation_attempts.get(ext, 0)
        
        if current_attempts >= max_attempts:
            api_logger.warning(f"추출기 생성 최대 재시도 초과: {ext}, GenericExtractor 강제 사용")
            fallback_instance = GenericExtractor()
            cls._instances[ext] = fallback_instance
            return fallback_instance
        
        # 등록된 추출기 클래스 찾기
        extractor_class = cls._extractors.get(ext)
        
        if extractor_class is None:
            api_logger.warning(f"지원하지 않는 파일 확장자: {ext}, GenericExtractor 사용")
            extractor_class = GenericExtractor
        
        # 인스턴스 생성 및 캐싱 (재시도 로직 포함)
        cls._instance_creation_attempts[ext] = current_attempts + 1
        
        try:
            instance = extractor_class()
            cls._instances[ext] = instance
            # 성공 시 재시도 카운터 리셋
            cls._instance_creation_attempts[ext] = 0
            api_logger.debug(f"추출기 인스턴스 생성됨: {ext} -> {extractor_class.__name__}")
            return instance
        except Exception as e:
            api_logger.error(f"추출기 인스턴스 생성 실패 (시도 {current_attempts + 1}/{max_attempts}): {extractor_class.__name__}, 오류: {e}")
            
            # 최대 재시도 도달 시 Fallback 사용
            if current_attempts + 1 >= max_attempts:
                api_logger.warning(f"추출기 생성 재시도 한계 도달: {ext}, GenericExtractor로 fallback")
                fallback_instance = GenericExtractor()
                cls._instances[ext] = fallback_instance
                return fallback_instance
            else:
                # 재시도를 위해 예외 재발생
                raise e
    
    @classmethod
    def get_supported_extensions(cls) -> List[str]:
        """지원하는 파일 확장자 목록 반환"""
        return list(cls._extractors.keys())
    
    @classmethod
    def clear_cache(cls):
        """인스턴스 캐시 초기화 (테스트용)"""
        cls._instances.clear()
        cls._instance_creation_attempts.clear()
        api_logger.debug("ExtractorRegistry 캐시 전체 초기화")
    
    @classmethod
    def invalidate_cache(cls, file_extension: str):
        """특정 확장자의 캐시 무효화"""
        ext = file_extension.lower()
        if ext in cls._instances:
            del cls._instances[ext]
            cls._instance_creation_attempts.pop(ext, None)
            api_logger.debug(f"추출기 캐시 무효화: {ext}")
    
    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """캐시 통계 정보 반환"""
        return {
            'cached_extractors': list(cls._instances.keys()),
            'failed_attempts': {k: v for k, v in cls._instance_creation_attempts.items() if v > 0},
            'total_registered': len(cls._extractors),
            'total_cached': len(cls._instances)
        }


@ExtractorRegistry.register(['py'])
class PythonExtractor(TreeSitterBaseExtractor):
    """Python 파일 함수 추출기 (tree-sitter 사용)"""
    
    def _get_language(self) -> Optional[Language]:
        """Python tree-sitter Language 반환"""
        try:
            return Language(tree_sitter_python.language())
        except Exception as e:
            api_logger.error(f"Python language 초기화 실패: {e}")
            return None
    
    def _get_function_query(self) -> str:
        """Python 함수/클래스 쿼리"""
        return """
        (function_definition
          name: (identifier) @func_name) @func_def
        
        (async_function_definition
          name: (identifier) @func_name) @func_def
        
        (class_definition
          name: (identifier) @class_name) @class_def
        """
    
    def _get_language_patterns(self) -> Dict[str, Any]:
        """Python 언어 패턴 정의 (컨텍스트 추출용)"""
        return {
            'line_comments': ['#'],
            'block_comments': [('"""', '"""'), ("'''", "'''")],
            'doc_comments': ['"""', "'''"],
            'decorators': ['@'],
            'stop_keywords': ['def', 'async def', 'class', 'import', 'from']
        }
    
    def _is_function_node(self, node: Node) -> bool:
        """Python 함수/클래스 노드 확인"""
        function_types = ['function_definition', 'async_function_definition', 'class_definition']
        return node.type in function_types
    
    def _extract_function_name(self, node: Node, content: bytes) -> str:
        """Python 함수명 추출"""
        for child in node.children:
            if child.type == 'identifier':
                return self._get_node_text(child, content)
        return "unknown_function"
    
    def _determine_function_type(self, node: Node) -> str:
        """Python 노드 타입 결정"""
        if node.type == 'class_definition':
            return 'class'
        elif node.type in ['function_definition', 'async_function_definition']:
            return 'method' if self._is_method(node) else 'function'
        return 'function'
    
    def _is_method(self, node: Node) -> bool:
        """클래스 내부 메서드인지 확인"""
        parent = node.parent
        while parent:
            if parent.type == 'class_definition':
                return True
            parent = parent.parent
        return False
    
    # tree-sitter 기반 추출을 위해 부모 클래스의 extract_functions 사용


@ExtractorRegistry.register(['js', 'ts'])
class JavaScriptExtractor(TreeSitterBaseExtractor):
    """JavaScript/TypeScript 파일 함수 추출기"""
    
    def _get_language(self) -> Optional[Language]:
        """JavaScript tree-sitter Language 반환"""
        try:
            return Language(tree_sitter_javascript.language())
        except Exception as e:
            api_logger.error(f"JavaScript language 초기화 실패: {e}")
            return None
    
    def _get_function_query(self) -> str:
        """JavaScript/TypeScript 함수 쿼리"""
        return """
        (function_declaration
          name: (identifier) @func_name) @func_def
        
        (arrow_function) @func_def
        
        (method_definition
          name: (property_identifier) @func_name) @func_def
        
        (class_declaration
          name: (identifier) @class_name) @class_def
        """
    
    def _get_language_patterns(self) -> Dict[str, Any]:
        """JavaScript/TypeScript 언어 패턴 정의 (컨텍스트 추출용)"""
        return {
            'line_comments': ['//'],
            'block_comments': [('/*', '*/'), ('/**', '*/')],
            'doc_comments': ['/**'],
            'decorators': ['@'],  # TypeScript 데코레이터
            'stop_keywords': ['function', 'class', 'const', 'let', 'var', 'import', 'export']
        }
    
    def _is_function_node(self, node: Node) -> bool:
        """JavaScript 함수/클래스 노드 확인"""
        function_types = [
            'function_declaration', 'arrow_function', 'method_definition',
            'class_declaration', 'function_expression'
        ]
        return node.type in function_types
    
    def _extract_function_name(self, node: Node, content: bytes) -> str:
        """JavaScript 함수명 추출"""
        # 함수 이름 찾기
        for child in node.children:
            if child.type in ['identifier', 'property_identifier']:
                return self._get_node_text(child, content)
        
        # 화살표 함수나 익명 함수의 경우
        if node.type == 'arrow_function':
            # 부모에서 변수명 찾기
            parent = node.parent
            if parent and parent.type == 'variable_declarator':
                for child in parent.children:
                    if child.type == 'identifier':
                        return self._get_node_text(child, content)
            return f"arrow_function_{node.start_point[0]}"
        
        return f"anonymous_{node.start_point[0]}"
    
    # tree-sitter 기반 추출을 위해 부모 클래스의 extract_functions 사용


@ExtractorRegistry.register(['java'])
class JavaExtractor(TreeSitterBaseExtractor):
    """Java 파일 함수 추출기"""
    
    def _get_language(self) -> Optional[Language]:
        """Java tree-sitter Language 반환"""
        try:
            return Language(tree_sitter_java.language())
        except Exception as e:
            api_logger.error(f"Java language 초기화 실패: {e}")
            return None
    
    def _get_function_query(self) -> str:
        """Java 메서드/클래스 쿼리"""
        return """
        (method_declaration
          name: (identifier) @method_name) @method_def
        
        (class_declaration
          name: (identifier) @class_name) @class_def
        """
    
    def _get_language_patterns(self) -> Dict[str, Any]:
        """Java 언어 패턴 정의 (컨텍스트 추출용)"""
        return {
            'line_comments': ['//'],
            'block_comments': [('/*', '*/'), ('/**', '*/')],
            'doc_comments': ['/**'],
            'decorators': ['@'],  # Java 어노테이션
            'stop_keywords': ['public', 'private', 'protected', 'class', 'interface', 'import', 'package']
        }
    
    def _is_function_node(self, node: Node) -> bool:
        """Java 메서드/클래스 노드 확인"""
        function_types = ['method_declaration', 'constructor_declaration', 'class_declaration']
        return node.type in function_types
    
    # tree-sitter 기반 추출을 위해 부모 클래스의 extract_functions 사용


@ExtractorRegistry.register(['c', 'cpp', 'cc', 'cxx'])
class CExtractor(TreeSitterBaseExtractor):
    """C/C++ 파일 함수 추출기"""
    
    def _get_language(self) -> Optional[Language]:
        """C/C++ tree-sitter Language 반환"""
        try:
            return Language(tree_sitter_cpp.language())
        except Exception as e:
            api_logger.error(f"C/C++ language 초기화 실패: {e}")
            return None
    
    def _get_function_query(self) -> str:
        """C/C++ 함수 쿼리"""
        return """
        (function_definition
          declarator: (function_declarator 
            declarator: (identifier) @func_name)) @func_def
        
        (class_specifier
          name: (type_identifier) @class_name) @class_def
        """
    
    def _get_language_patterns(self) -> Dict[str, Any]:
        """C/C++ 언어 패턴 정의 (컨텍스트 추출용)"""
        return {
            'line_comments': ['//'],
            'block_comments': [('/*', '*/'), ('/**', '*/')],
            'doc_comments': ['/**'],
            'decorators': ['[['],  # C++11 attributes
            'stop_keywords': ['int', 'void', 'char', 'float', 'double', 'struct', 'class', 'typedef', '#include', '#define']
        }
    
    def _is_function_node(self, node: Node) -> bool:
        """C/C++ 함수/클래스 노드 확인"""
        function_types = ['function_definition', 'class_specifier', 'struct_specifier']
        return node.type in function_types
    
    # tree-sitter 기반 추출을 위해 부모 클래스의 extract_functions 사용


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


def _validate_diff_info(diff_info: Dict[int, Dict], file_content: str, filename: str) -> Dict[int, Dict]:
    """diff_info의 라인 번호가 파일 범위 내에 있는지 검증하고 정리"""
    if not diff_info:
        return diff_info
    
    total_lines = len(file_content.splitlines())
    validated_diff = {}
    invalid_lines = []
    
    for line_num, change_info in diff_info.items():
        if 1 <= line_num <= total_lines:
            validated_diff[line_num] = change_info
        else:
            invalid_lines.append(line_num)
    
    if invalid_lines:
        api_logger.warning(f"파일 '{filename}' 범위 초과 diff 라인 제거: {invalid_lines} (총 {total_lines}줄)")
    
    return validated_diff


# 메인 함수
async def extract_functions_by_type(file_content: str, filename: str, diff_info: Dict[int, Dict]) -> List[Dict[str, Any]]:
    """파일 타입에 따라 적절한 추출기를 사용하여 함수들을 추출"""
    
    # diff_info 검증 및 정리
    validated_diff_info = _validate_diff_info(diff_info, file_content, filename)
    
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
        functions = await extractor.extract_functions(file_content, filename, validated_diff_info)
        
        api_logger.info(f"파일 '{filename}' 함수 추출 완료: {len(functions)}개 함수")
        return functions
        
    except Exception as e:
        api_logger.error(f"파일 '{filename}' 함수 추출 실패: {str(e)}")
        
        # 에러 발생 시 Fallback으로 GenericExtractor 사용
        try:
            fallback_extractor = GenericExtractor()
            return await fallback_extractor.extract_functions(file_content, filename, validated_diff_info)
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
                'changes': validated_diff_info,
                'has_changes': bool(validated_diff_info),
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


def get_extractor_cache_stats() -> Dict[str, Any]:
    """추출기 캐시 통계 정보 반환"""
    return ExtractorRegistry.get_cache_stats()


def clear_extractor_cache():
    """추출기 캐시 초기화"""
    ExtractorRegistry.clear_cache()
    api_logger.info("추출기 캐시가 초기화되었습니다")