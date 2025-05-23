from redis import Redis
from supabase._async.client import AsyncClient
from typing import Dict, List, Any, Tuple, Optional
from app.utils.logger import api_logger
import asyncio
import re
import json
import time
import ast

class CodeAnalysisService:
    """함수 중심 코드 분석 및 LLM 처리 서비스"""
    def __init__(self, redis_client: Redis, supabase: AsyncClient):
        self.redis_client = redis_client
        self.supabase = supabase
        self.function_queue = asyncio.Queue()  # 함수별 분석 큐
    
    async def analyze_code_changes(self, files: List[Dict], owner: str, repo: str, commit_sha: str, user_id: str):
        """코드 변경 분석 진입점 - 변경된 함수만 처리"""
        api_logger.info(f"커밋 {commit_sha[:8]} 함수별 분석 시작: {len(files)}개 파일")
        
        # 통계 정보
        total_functions_analyzed = 0
        changed_functions = 0
        new_functions = 0
        cached_functions = 0
        
        for file in files:
            filename = file.get('filename', 'unknown')
            
            if "patch" not in file:
                api_logger.info(f"파일 '{filename}': 패치 정보 없음, 건너뜀")
                continue
            
            # diff에서 변경된 라인 정보 추출
            diff_info = self._extract_detailed_diff(file.get("patch", ""))
            
            if not diff_info:
                api_logger.info(f"파일 '{filename}': 변경 사항 없음, 건너뜀")
                continue
            
            # 패치에서 현재 코드 상태 재구성 (전체 파일 내용 대신)
            file_content, _ = self._parse_patch_with_context(file["patch"])
            
            # 파일을 함수 단위로 분해하고 변경 여부 판단
            functions = await self._extract_functions_from_file(file_content, filename, diff_info)
            
            # 변경된 함수만 필터링
            changed_or_new_functions = []
            for func_info in functions:
                function_cache_key = f"{user_id}:{commit_sha}:{filename}:{func_info['name']}"
                
                # 이미 분석된 함수는 스킵
                if self.redis_client.exists(function_cache_key):
                    cached_functions += 1
                    api_logger.debug(f"함수 '{func_info['name']}': 이미 분석 완료, 스킵")
                    continue
                
                # 변경이 있는 함수만 처리
                if func_info.get('has_changes', False):
                    changed_or_new_functions.append(func_info)
                    if self._is_new_function(user_id, filename, func_info['name']):
                        new_functions += 1
                        api_logger.info(f"함수 '{func_info['name']}': 새로운 함수 감지")
                    else:
                        changed_functions += 1
                        api_logger.info(f"함수 '{func_info['name']}': 변경 사항 감지")
                else:
                    api_logger.debug(f"함수 '{func_info['name']}': 변경 없음, 큐에 추가하지 않음")
            
            # 변경된 함수들만 큐에 추가
            for func_info in changed_or_new_functions:
                await self._enqueue_function_analysis(func_info, commit_sha, user_id, owner, repo)
                total_functions_analyzed += 1
            
            if changed_or_new_functions:
                api_logger.info(f"파일 '{filename}': {len(changed_or_new_functions)}개 변경된 함수만 분석 큐에 추가")
            else:
                api_logger.info(f"파일 '{filename}': 변경된 함수 없음, 분석 스킵")
        
        # 최종 통계 로그
        api_logger.info(f"커밋 {commit_sha[:8]} 분석 준비 완료: 변경된 함수 {changed_functions}개, 새 함수 {new_functions}개, 캐시된 함수 {cached_functions}개")
    

    def _is_new_function(self, user_id: str, filename: str, func_name: str) -> bool:
        """함수가 새로 추가된 것인지 확인 (이전 커밋에 존재하지 않았던 함수)"""
        # 해당 함수의 이전 커밋 분석 결과가 있는지 확인
        pattern = f"{user_id}:*:{filename}:{func_name}"
        
        cursor = 0
        while True:
            cursor, keys = self.redis_client.scan(cursor, match=pattern, count=100)
            if keys:
                return False  # 이전 분석 결과가 있으면 새로운 함수가 아님
            if cursor == 0:
                break
        
        return True  # 이전 분석 결과가 없으면 새로운 함수
        
    async def _enqueue_function_analysis(self, func_info: Dict, commit_sha: str, user_id: str, 
                                       owner: str, repo: str, priority: bool = False):
        """함수별 분석 작업을 큐에 추가 - 우선순위 지원"""
        # 메타데이터에서 참조 정보 추출

        """함수별 분석 작업을 큐에 추가"""
        # 메타데이터에서 참조 정보 추출
        metadata = self._extract_function_metadata(func_info['code'])
        
        analysis_item = {
            'function_info': func_info,
            'commit_sha': commit_sha,
            'user_id': user_id,
            'owner': owner,
            'repo': repo,
            'metadata': metadata,
            'cache_key': f"{user_id}:{commit_sha}:{func_info['filename']}:{func_info['name']}"
        }
        
        await self.function_queue.put(analysis_item)
        api_logger.info(f"함수 '{func_info['name']}' 분석 큐에 추가됨")
        
    
    async def process_queue(self):
        """함수별 분석 큐 처리"""
        api_logger.info("함수별 분석 큐 처리 시작")
        
        while not self.function_queue.empty():
            try:
                item = await self.function_queue.get()
                await self._analyze_function(item)
                self.function_queue.task_done()
            except Exception as e:
                api_logger.error(f"함수 분석 처리 오류: {e}")
                continue
        
        api_logger.info("모든 함수 분석 완료")
    
    def _extract_detailed_diff(self, patch: str) -> Dict[int, Dict]:
        """diff 패치에서 상세 변경 정보 추출(라인)"""
        changes = {}
        current_line = 0
        
        lines = patch.splitlines()
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # @@ -a,b +c,d @@ 형식 헤더 찾기
            hunk_match = re.match(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', line)
            if hunk_match:
                current_line = int(hunk_match.group(1))
                i += 1
                continue
            
            # 삭제된 라인
            if line.startswith('-') and not line.startswith('---'):
                old_code = line[1:]
                # 다음 라인이 추가 라인인지 확인 (수정)
                if i + 1 < len(lines) and lines[i + 1].startswith('+'):
                    new_code = lines[i + 1][1:]
                    changes[current_line] = {
                        "type": "modified",
                        "old": old_code,
                        "new": new_code
                    }
                    i += 2  # 두 라인 모두 처리
                    current_line += 1
                else:
                    changes[current_line] = {
                        "type": "deleted",
                        "old": old_code,
                        "new": ""
                    }
                    i += 1
                continue
            
            # 추가된 라인
            elif line.startswith('+') and not line.startswith('+++'):
                changes[current_line] = {
                    "type": "added",
                    "old": "",
                    "new": line[1:]
                }
                current_line += 1
                i += 1
                continue
            
            # 컨텍스트 라인 (변경 없음)
            else:
                current_line += 1
                i += 1
        
        return changes
    
    def _parse_patch_with_context(self, patch: str) -> Tuple[str, Dict[int, Dict]]:
        """패치에서 코드와 변경 정보 동시 추출 - 기존과 동일"""
        diff_info = self._extract_detailed_diff(patch)
        
        # 패치에서 최종 코드 상태 재구성
        lines = []
        current_line = 1
        
        for patch_line in patch.splitlines():
            if patch_line.startswith(("diff ", "index ", "--- ", "+++ ", "@@")):
                continue
            
            if patch_line.startswith('-'):
                continue  # 삭제된 라인은 제외
            elif patch_line.startswith('+'):
                lines.append(patch_line[1:])  # 추가된 라인
            else:
                lines.append(patch_line)  # 컨텍스트 라인
        
        return '\n'.join(lines), diff_info
    
    async def _extract_functions_from_file(self, file_content: str, filename: str, diff_info: Dict) -> List[Dict]:
        """파일에서 함수/메서드를 개별적으로 추출"""
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        
        #python일 경우, ast사용
        if ext == 'py':
            return await self._extract_python_functions(file_content, filename, diff_info)
        else:
            return await self._extract_generic_functions(file_content, filename, diff_info, ext)
    
    async def _extract_python_functions(self, file_content: str, filename: str, diff_info: Dict) -> List[Dict]:
        """Python 파일에서 함수/메서드 개별 추출 (AST 사용)"""
        functions = []
        
        try:
            tree = ast.parse(file_content)
            lines = file_content.splitlines()
            print(lines)
            # 전역 임포트 및 상수 수집
            global_code = []
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
                            
                            # 메서드 코드 추출
                            method_code = '\n'.join(lines[method_start-1:method_end])
                            
                            # 메서드 관련 변경 사항 찾기
                            method_changes = {
                                line_num: change for line_num, change in diff_info.items()
                                if method_start <= line_num <= method_end
                            }
                            
                            function_name = f"{node.name}.{item.name}"  # 클래스.메서드 형식
                            
                            functions.append({
                                'name': function_name,
                                'type': 'method',
                                'code': method_code,
                                'start_line': method_start,
                                'end_line': method_end,
                                'filename': filename,
                                'class_name': node.name,
                                'changes': method_changes,
                                'has_changes': bool(method_changes)
                            })
                            
                            # 함수 라인 기록
                            function_lines.update(range(method_start, method_end + 1))
                
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
                        
                        func_code = '\n'.join(lines[func_start-1:func_end])
                        
                        func_changes = {
                            line_num: change for line_num, change in diff_info.items()
                            if func_start <= line_num <= func_end
                        }
                        
                        functions.append({
                            'name': node.name,
                            'type': 'function',
                            'code': func_code,
                            'start_line': func_start,
                            'end_line': func_end,
                            'filename': filename,
                            'changes': func_changes,
                            'has_changes': bool(func_changes)
                        })
                        
                        function_lines.update(range(func_start, func_end + 1))
            
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
            print(functions)
            return functions
            
        except SyntaxError as e:
            api_logger.error(f"Python 파일 파싱 오류: {e}")
            # 파싱 실패 시 전체 파일을 하나의 함수로 처리
            return [{
                'name': 'entire_file',
                'type': 'file',
                'code': file_content,
                'start_line': 1,
                'end_line': len(file_content.splitlines()),
                'filename': filename,
                'changes': diff_info,
                'has_changes': bool(diff_info)
            }]
    
    async def _extract_generic_functions(self, file_content: str, filename: str, diff_info: Dict, ext: str) -> List[Dict]:
        """일반 언어의 함수 추출 (정규식 기반)"""
        functions = []
        lines = file_content.splitlines()
        
        # 언어별 함수 패턴
        patterns = {
            'js': r'(?:function\s+(\w+)|const\s+(\w+)\s*=.*?function|(\w+)\s*:\s*(?:async\s+)?function)',
            'ts': r'(?:function\s+(\w+)|const\s+(\w+)\s*=.*?function|(\w+)\s*:\s*(?:async\s+)?function)',
            'java': r'(?:public|private|protected)?\s*(?:static\s+)?[\w<>]+\s+(\w+)\s*\(',
            'c': r'[\w\*\s]+\s+(\w+)\s*\([^)]*\)\s*\{',
            'cpp': r'[\w\*\s:]+\s+(\w+)\s*\([^)]*\)\s*\{',
        }
        
        pattern = patterns.get(ext, r'[\w\s]+\s+(\w+)\s*\([^)]*\)\s*\{')
        
        for match in re.finditer(pattern, file_content, re.MULTILINE):
            func_name = next((g for g in match.groups() if g), "unknown")
            func_start_pos = match.start()
            
            # 함수 시작 라인 계산
            func_start_line = file_content[:func_start_pos].count('\n') + 1
            
            # 중괄호 매칭으로 함수 끝 찾기
            func_end_line = self._find_function_end(file_content, func_start_pos)
            
            if func_end_line > func_start_line:
                func_code = '\n'.join(lines[func_start_line-1:func_end_line])
                
                func_changes = {
                    line_num: change for line_num, change in diff_info.items()
                    if func_start_line <= line_num <= func_end_line
                }
                
                functions.append({
                    'name': func_name,
                    'type': 'function',
                    'code': func_code,
                    'start_line': func_start_line,
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
                'code': file_content,
                'start_line': 1,
                'end_line': len(lines),
                'filename': filename,
                'changes': diff_info,
                'has_changes': bool(diff_info)
            })
        
        return functions
    
    def _find_function_end(self, content: str, start_pos: int) -> int:
        """중괄호 매칭으로 함수 끝 위치 찾기"""
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
    
    def _extract_function_metadata(self, code: str) -> Dict[str, Any]:
        """함수 코드에서 메타데이터 추출"""
        metadata = {}
        
        for i, line in enumerate(code.splitlines()[:10]):  # 첫 10줄만 검사
            line = line.strip()
            if line.startswith('#'):
                # #[참조파일.py]{리턴타입}(요구사항) 형식 파싱
                pattern = r'#\[([^\]]+)\]\{([^}]+)\}\(([^)]+)\)(.*)'
                match = re.match(pattern, line)
                if match:
                    metadata['reference_file'] = match.group(1)
                    metadata['return_type'] = match.group(2)
                    metadata['requirements'] = match.group(3)
                    metadata['custom_prompt'] = match.group(4).strip()
                    break
                
                # 단순 참조 파일만 있는 경우: #[파일.py]
                ref_match = re.search(r'\[([^\]]+\.py)\]', line)
                if ref_match:
                    metadata['reference_file'] = ref_match.group(1)
        
        return metadata
    
    async def process_queue(self):
        """함수별 분석 큐 처리"""
        api_logger.info("함수별 분석 큐 처리 시작")
        
        while not self.function_queue.empty():
            try:
                item = await self.function_queue.get()
                await self._analyze_function(item)
                self.function_queue.task_done()
            except Exception as e:
                api_logger.error(f"함수 분석 처리 오류: {e}")
                continue
        
        api_logger.info("모든 함수 분석 완료")
    
    async def _analyze_function(self, item: Dict):
        """개별 함수 분석 처리 - 캐시 키 개선"""
        func_info = item['function_info']
        func_name = func_info['name']
        filename = func_info['filename']
        user_id = item['user_id']
        commit_sha = item['commit_sha']
        cache_key = item['cache_key']
        
        api_logger.info(f"함수 '{func_name}' 분석 시작 (커밋: {commit_sha[:8]})")
        
        # 분석 시작 전 다시 한번 캐시 확인 (동시성 처리)
        if self.redis_client.exists(cache_key):
            api_logger.info(f"함수 '{func_name}': 다른 프로세스에서 이미 분석 완료, 스킵")
            return
        
        # 이전 커밋에서의 분석 결과 조회 (개선된 버전)
        previous_summary = await self._get_previous_function_analysis(
            user_id, filename, func_name, commit_sha
        )
        
        # 참조 파일 내용 가져오기
        reference_content = None
        if 'reference_file' in item['metadata']:
            reference_content = await self._fetch_reference_function(
                item['metadata']['reference_file'], 
                item['owner'], 
                item['repo'], 
                commit_sha
            )
        
        # 함수가 길면 청크로 분할
        chunks = self._split_function_if_needed(func_info['code'])
        
        if len(chunks) == 1:
            # 단일 청크 처리
            summary = await self._call_llm_for_function(
                func_info, 
                chunks[0], 
                item['metadata'], 
                previous_summary, 
                reference_content,
                commit_sha
            )
        else:
            # 다중 청크 연속 처리
            summary = await self._process_multi_chunk_function(
                func_info, 
                chunks, 
                item['metadata'], 
                previous_summary, 
                reference_content,
                commit_sha
            )
        
        # 새로운 Redis 키 구조로 저장
        self.redis_client.setex(cache_key, 86400 * 7, summary)  # 7일 보관
        
        # 이전 호환성을 위한 레거시 키도 설정 (선택적)
        legacy_key = f"func:{filename}:{func_name}"
        self.redis_client.setex(legacy_key, 86400 * 7, summary)
        
        # Notion 업데이트는 파일 단위로 별도 처리
        await self._update_notion_if_needed(func_info, summary, user_id, commit_sha)
        
        api_logger.info(f"함수 '{func_name}' 분석 완료 (커밋: {commit_sha[:8]})")

    async def _get_previous_function_analysis(self, user_id: str, filename: str, 
                                            func_name: str, current_commit: str) -> Optional[str]:
        """이전 커밋에서의 함수 분석 결과 조회"""
        
        # 1. 동일 함수의 이전 커밋 분석 결과 검색
        pattern = f"{user_id}:*:{filename}:{func_name}"
        matching_keys = []
        
        # Redis SCAN을 사용하여 패턴 매칭 키 조회
        cursor = 0
        while True:
            cursor, keys = self.redis_client.scan(cursor, match=pattern, count=100)
            matching_keys.extend(keys)
            if cursor == 0:
                break
        
        # 현재 커밋 제외하고 가장 최근 분석 결과 반환
        previous_keys = [key for key in matching_keys if current_commit not in key]
        
        if previous_keys:
            # 키 이름을 기준으로 정렬 (최근 것부터)
            previous_keys.sort(reverse=True)
            latest_key = previous_keys[0]
            
            previous_analysis = self.redis_client.get(latest_key)
            if previous_analysis:
                # 이전 커밋 해시 추출
                previous_commit = latest_key.split(':')[1]
                api_logger.info(f"함수 '{func_name}': 이전 커밋 {previous_commit[:8]} 분석 결과 활용")
                return previous_analysis
        
        api_logger.debug(f"함수 '{func_name}': 이전 분석 결과 없음, 새로 분석")
        return None

    def _split_function_if_needed(self, code: str, max_length: int = 2000) -> List[str]:
        """함수가 너무 길면 청크로 분할"""
        if len(code) <= max_length:
            return [code]
        
        # 단순 길이 기반 분할 (복잡한 정규식 제거)
        chunks = []
        for i in range(0, len(code), max_length):
            chunks.append(code[i:i + max_length])
        
        return chunks
    
    async def _process_multi_chunk_function(self, func_info: Dict, chunks: List[str], 
                                          metadata: Dict, previous_summary: str, 
                                          reference_content: str, commit_sha: str) -> str:
        """다중 청크 함수의 연속적 요약 처리"""
        current_summary = previous_summary
        
        for i, chunk in enumerate(chunks):
            api_logger.info(f"함수 '{func_info['name']}' 청크 {i+1}/{len(chunks)} 처리")
            
            # 이전 요약을 포함한 LLM 호출
            chunk_summary = await self._call_llm_for_function(
                func_info, 
                chunk, 
                metadata, 
                current_summary,  # 이전 요약 포함
                reference_content,
                commit_sha,
                chunk_index=i,
                total_chunks=len(chunks)
            )
            
            current_summary = chunk_summary  # 다음 청크에서 사용할 요약 업데이트
        
        return current_summary
    
    async def _call_llm_for_function(self, func_info: Dict, code: str, metadata: Dict, 
                                   previous_summary: str = None, reference_content: str = None,
                                   commit_sha: str = None, chunk_index: int = 0, total_chunks: int = 1) -> str:
        """함수별 LLM 분석 호출 - 커밋 정보 포함"""
        
        # 프롬프트 구성
        prompt_parts = []
        
        # 커밋 정보 추가
        if commit_sha:
            prompt_parts.append(f"🔍 커밋 {commit_sha[:8]}에서 분석하는 함수입니다.")
        
        # 기본 시스템 프롬프트
        if total_chunks > 1:
            prompt_parts.append(f"다음은 '{func_info['name']}' 함수의 {chunk_index+1}/{total_chunks} 청크입니다.")
        else:
            prompt_parts.append(f"다음은 '{func_info['name']}' 함수의 코드입니다.")
        
        # 이전 요약이 있으면 포함
        if previous_summary:
            prompt_parts.append(f"\n📋 이전 분석 결과:\n{previous_summary}")
            if total_chunks > 1:
                prompt_parts.append("\n위 분석을 바탕으로 다음 코드 청크를 분석하고 통합된 요약을 제공하세요.")
            else:
                prompt_parts.append("\n위 분석을 참고하여 변경사항을 중심으로 업데이트된 분석을 제공하세요.")
        
        # 참조 파일 내용 포함
        if reference_content:
            prompt_parts.append(f"\n🔗 참조 함수 코드:\n{reference_content}")
        
        # 메타데이터 기반 커스텀 프롬프트
        if 'custom_prompt' in metadata:
            prompt_parts.append(f"\n📝 추가 요구사항: {metadata['custom_prompt']}")
        
        if 'return_type' in metadata:
            prompt_parts.append(f"\n↩️ 예상 반환 타입: {metadata['return_type']}")
        
        if 'requirements' in metadata:
            prompt_parts.append(f"\n⚙️ 구현 요구사항: {metadata['requirements']}")
        
        # 변경 사항이 있으면 강조
        if func_info.get('has_changes', False):
            changes_text = []
            for line_num, change in func_info.get('changes', {}).items():
                if change['type'] == 'modified':
                    changes_text.append(f"라인 {line_num}: '{change['old']}' → '{change['new']}'")
                elif change['type'] == 'added':
                    changes_text.append(f"라인 {line_num}: 추가됨 - '{change['new']}'")
                elif change['type'] == 'deleted':
                    changes_text.append(f"라인 {line_num}: 삭제됨 - '{change['old']}'")
            
            if changes_text:
                prompt_parts.append(f"\n🔥 이번 커밋 주요 변경사항:\n" + "\n".join(changes_text))
                prompt_parts.append("\n특히 위 변경사항의 목적과 영향을 중점적으로 분석해주세요.")
        else:
            prompt_parts.append(f"\n✅ 이번 커밋에서 이 함수는 변경되지 않았습니다.")
        
        # 분석할 코드
        prompt_parts.append(f"\n📄 분석할 코드:\n```{func_info.get('filename', '').split('.')[-1]}\n{code}\n```")
        
        # 응답 형식 지정
        prompt_parts.append("""
📊 분석 결과를 다음 형식으로 제공하세요:
1. **🎯 기능 요약**: 함수의 핵심 목적을 한 문장으로
2. **⚙️ 주요 로직**: 핵심 알고리즘이나 처리 흐름
3. **🔄 변경 영향**: (변경사항이 있는 경우) 변경으로 인한 동작 변화
4. **🔗 의존성**: 사용하는 외부 함수나 라이브러리
5. **💡 개선 제안**: (필요시) 코드 품질 향상 방안
""")
        
        full_prompt = "\n".join(prompt_parts)
        print(full_prompt)
        # TODO: 실제 LLM API 호출 구현
        # 임시 응답 - 커밋 정보 포함
        return f"[LLM 분석 결과 - 커밋 {commit_sha[:8] if commit_sha else 'unknown'}] {func_info['name']} 함수: {func_info.get('type', 'function')} 타입"
    
    async def _fetch_reference_function(self, reference_file: str, owner: str, repo: str, commit_sha: str) -> str:
        """참조 파일의 함수 요약을 Redis에서 조회"""
        # 파일에서 특정 함수가 지정되었는지 확인
        if '#' in reference_file:
            file_path, func_name = reference_file.split('#', 1)
            redis_key = f"func:{file_path}:{func_name}"
        else:
            # 파일 전체 참조인 경우 주요 함수들 조회
            redis_key = f"func:{reference_file}:*"
        
        cached_content = self.redis_client.get(redis_key)
        if cached_content:
            return cached_content
        
        # Redis에 없으면 파일 내용 요청 (기존 방식 활용)
        return await self._request_reference_file_content(reference_file, owner, repo, commit_sha)
    
    async def _request_reference_file_content(self, reference_file: str, owner: str, repo: str, commit_sha: str) -> str:
        """GitHub에서 참조 파일 내용 요청 (기존 방식 유지)"""
        # 기존 구현과 동일한 Redis 키-값 방식 사용
        request_id = f"ref_{int(time.time())}_{hash(reference_file) % 1000}"
        
        request_data = {
            'path': reference_file,
            'commit_sha': commit_sha,
            'request_id': request_id
        }
        
        request_key = f"ref_request:{owner}:{repo}:{request_id}"
        response_key = f"ref_response:{owner}:{repo}:{request_id}"
        
        self.redis_client.setex(request_key, 300, json.dumps(request_data))
        
        # 5초 폴링 대기
        for _ in range(10):
            response_str = self.redis_client.get(response_key)
            if response_str:
                response_data = json.loads(response_str)
                if response_data.get('status') == 'success':
                    return response_data.get('content', '')
            await asyncio.sleep(0.5)
        
        return ""
    
    async def _update_notion_if_needed(self, func_info: Dict, summary: str, user_id: str, commit_sha: str):
        """파일별 종합 분석 및 Notion 업데이트"""
        filename = func_info['filename']
        
        # 1. 파일의 모든 함수 분석이 완료되었는지 확인
        if await self._is_file_analysis_complete(filename, user_id, commit_sha):
            # 2. 파일별 종합 분석 수행
            file_summary = await self._generate_file_level_analysis(filename, user_id)
            
            # 3. Notion AI 요약 블록 업데이트
            await self._update_notion_ai_block(filename, file_summary, user_id)
            
            # 4. 아키텍처 개선 제안 생성
            await self._generate_architecture_suggestions(filename, file_summary, user_id)

    async def _is_file_analysis_complete(self, filename: str, user_id: str, commit_sha: str) -> bool:
        """특정 커밋에서 파일의 모든 함수 분석이 완료되었는지 확인"""
        
        # 해당 커밋과 파일의 모든 함수 키 조회
        pattern = f"{user_id}:{commit_sha}:{filename}:*"
        function_keys = []
        
        cursor = 0
        while True:
            cursor, keys = self.redis_client.scan(cursor, match=pattern, count=100)
            function_keys.extend(keys)
            if cursor == 0:
                break
        
        # 분석 대기 중인 함수가 있는지 큐에서 확인
        temp_queue = []
        pending_functions = set()
        
        # 큐에서 해당 파일의 대기 중인 함수들 확인
        while not self.function_queue.empty():
            item = await self.function_queue.get()
            temp_queue.append(item)
            
            if (item['function_info']['filename'] == filename and 
                item['commit_sha'] == commit_sha and 
                item['user_id'] == user_id):
                pending_functions.add(item['function_info']['name'])
        
        # 큐에 다시 넣기
        for item in temp_queue:
            await self.function_queue.put(item)
        
        # 대기 중인 함수가 없고, 분석된 함수가 있으면 완료
        return len(pending_functions) == 0 and len(function_keys) > 0
    
    def _extract_detailed_diff(self, patch: str) -> Dict[int, Dict]:
        """diff 패치에서 상세 변경 정보 추출(라인) - 기존과 동일"""
        changes = {}
        current_line = 0
        
        lines = patch.splitlines()
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # @@ -a,b +c,d @@ 형식 헤더 찾기
            hunk_match = re.match(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', line)
            if hunk_match:
                current_line = int(hunk_match.group(1))
                i += 1
                continue
            
            # 삭제된 라인
            if line.startswith('-') and not line.startswith('---'):
                old_code = line[1:]
                # 다음 라인이 추가 라인인지 확인 (수정)
                if i + 1 < len(lines) and lines[i + 1].startswith('+'):
                    new_code = lines[i + 1][1:]
                    changes[current_line] = {
                        "type": "modified",
                        "old": old_code,
                        "new": new_code
                    }
                    i += 2  # 두 라인 모두 처리
                    current_line += 1
                else:
                    changes[current_line] = {
                        "type": "deleted",
                        "old": old_code,
                        "new": ""
                    }
                    i += 1
                continue
            
            # 추가된 라인
            elif line.startswith('+') and not line.startswith('+++'):
                changes[current_line] = {
                    "type": "added",
                    "old": "",
                    "new": line[1:]
                }
                current_line += 1
                i += 1
                continue
            
            # 컨텍스트 라인 (변경 없음)
            else:
                current_line += 1
                i += 1
        
        return changes

    async def _generate_file_level_analysis(self, filename: str, user_id: str) -> str:
        """파일 전체 흐름 분석 및 종합 요약 생성"""
        
        # 1. 파일의 모든 함수 요약 수집
        pattern = f"func:{filename}:*"
        function_keys = self.redis_client.keys(pattern)
        
        function_summaries = {}
        for key in function_keys:
            function_name = key.split(":")[-1]  # func:파일:함수명 → 함수명
            summary = self.redis_client.get(key)
            if summary:
                function_summaries[function_name] = summary
        
        # 2. 함수들을 타입별로 분류
        categorized_functions = {
            'global': [],           # 전역 코드
            'class_methods': {},    # 클래스별 메서드 그룹
            'functions': [],        # 독립 함수
            'helpers': []          # 헬퍼 함수
        }
        
        for func_name, summary in function_summaries.items():
            if func_name == 'globals_and_imports':
                categorized_functions['global'].append(summary)
            elif '.' in func_name:  # 클래스.메서드 형식
                class_name, method_name = func_name.split('.', 1)
                if class_name not in categorized_functions['class_methods']:
                    categorized_functions['class_methods'][class_name] = []
                categorized_functions['class_methods'][class_name].append({
                    'method': method_name,
                    'summary': summary
                })
            elif func_name.startswith('_'):
                categorized_functions['helpers'].append({
                    'function': func_name,
                    'summary': summary
                })
            else:
                categorized_functions['functions'].append({
                    'function': func_name,
                    'summary': summary
                })
        
        # 3. 파일 전체 분석 프롬프트 구성
        analysis_prompt = f"""
    파일명: {filename}

    다음은 이 파일의 모든 함수별 분석 결과입니다. 
    전체적인 아키텍처 흐름과 개선방안을 분석해주세요.

    ## 📋 함수별 분석 결과

    ### 🌍 전역 코드 (임포트/상수)
    {categorized_functions['global'][0] if categorized_functions['global'] else '없음'}

    """

        # 클래스별 메서드 추가
        for class_name, methods in categorized_functions['class_methods'].items():
            analysis_prompt += f"""
    ### 🏗️ {class_name} 클래스
    """
            for method in methods:
                analysis_prompt += f"""
    **{method['method']}():**
    {method['summary']}

    """

        # 독립 함수들 추가
        if categorized_functions['functions']:
            analysis_prompt += """
    ### ⚡ 독립 함수들
    """
            for func in categorized_functions['functions']:
                analysis_prompt += f"""
    **{func['function']}():**
    {func['summary']}

    """

        # 헬퍼 함수들 추가
        if categorized_functions['helpers']:
            analysis_prompt += """
    ### 🔧 헬퍼 함수들
    """
            for helper in categorized_functions['helpers']:
                analysis_prompt += f"""
    **{helper['function']}():**
    {helper['summary']}

    """

        # 분석 요청 추가
        analysis_prompt += """
    ## 🎯 전체 분석 요청

    다음 관점에서 종합 분석해주세요:

    ### 1. **🏛️ 아키텍처 분석**
    - 전체적인 설계 패턴과 구조
    - 클래스와 함수들 간의 관계
    - 책임 분리가 잘 되어있는지

    ### 2. **🔄 데이터 흐름 분석**  
    - 주요 데이터가 어떻게 처리되는지
    - 함수들 간의 호출 관계와 의존성
    - 병목 구간이나 개선 포인트

    ### 3. **🚀 성능 및 확장성**
    - 성능상 문제가 될 수 있는 부분
    - 확장성을 위한 개선 방안
    - 메모리 사용 최적화 포인트

    ### 4. **🛡️ 안정성 및 에러 처리**
    - 예외 처리가 충분한지
    - 엣지 케이스 대응 방안
    - 로깅 및 모니터링 개선점

    ### 5. **📈 코드 품질 평가**
    - 가독성 및 유지보수성
    - 중복 코드나 리팩토링 대상
    - 테스트 가능성

    ### 6. **🎯 구체적 개선 제안**
    - 우선순위별 개선 사항 (상/중/하)
    - 각 개선사항의 예상 효과
    - 구현 난이도 및 소요 시간 추정

    **응답 형식:** 마크다운으로 구조화하여 Notion에서 읽기 좋게 작성
    """
        print(analysis_prompt)
        # 4. LLM 호출하여 종합 분석
        file_analysis = await self._call_llm_for_file_analysis(analysis_prompt)
        
        # 5. 분석 결과를 Redis에 캐싱 (파일 단위)
        file_cache_key = f"file_analysis:{filename}"
        self.redis_client.setex(file_cache_key, 86400 * 3, file_analysis)  # 3일 보관
        
        return file_analysis

    async def _call_llm_for_file_analysis(self, prompt: str) -> str:
        """파일 전체 분석을 위한 LLM 호출"""
        
        # TODO: 실제 LLM API 호출
        # response = await openai.ChatCompletion.acreate(
        #     model="gpt-4-turbo",  # 긴 컨텍스트를 위해 turbo 모델 사용
        #     messages=[
        #         {"role": "system", "content": "당신은 시니어 소프트웨어 아키텍트입니다. 코드의 전체적인 구조와 개선방안을 분석하는 전문가입니다."},
        #         {"role": "user", "content": prompt}
        #     ],
        #     temperature=0.3,
        #     max_tokens=2000
        # )
        # return response.choices[0].message.content
        
        # 임시 응답
        print(prompt)
        return f"""
    # 📊 {prompt.split('파일명: ')[1].split()[0]} 전체 분석 보고서

    ## 🏛️ 아키텍처 분석
    - **설계 패턴**: 서비스 레이어 패턴 적용
    - **구조**: 잘 모듈화된 클래스 중심 설계
    - **책임 분리**: 각 함수가 단일 책임 원칙을 잘 준수

    ## 🔄 데이터 흐름 분석
    - **주요 흐름**: 파일 → 함수 추출 → 개별 분석 → 큐 처리
    - **병목 구간**: LLM API 호출 부분에서 지연 가능성
    - **개선 포인트**: 병렬 처리 도입 가능

    ## 🚀 성능 및 확장성
    - **성능**: Redis 캐싱으로 효율적 처리
    - **확장성**: 큐 기반 설계로 확장 용이
    - **최적화**: 함수 분할 로직 개선 여지

    ## 🛡️ 안정성 및 에러 처리
    - **예외 처리**: try-catch 블록 충분히 활용
    - **로깅**: 각 단계별 로깅 잘 구현
    - **개선**: 타임아웃 처리 추가 필요

    ## 📈 코드 품질 평가
    ⭐⭐⭐⭐⭐ (5/5)
    - **가독성**: 매우 우수
    - **유지보수성**: 모듈화 잘 됨
    - **테스트 가능성**: 각 함수가 독립적

    ## 🎯 구체적 개선 제안

    ### 🔥 상순위 (즉시 적용)
    1. **LLM API 실제 연동** - 2시간 소요
    2. **병렬 처리 도입** - 4시간 소요

    ### 🚀 중순위 (1주 내)
    1. **에러 재시도 로직 강화** - 6시간 소요
    2. **모니터링 대시보드 추가** - 1일 소요

    ### 💡 하순위 (장기)
    1. **ML 기반 코드 품질 예측** - 1주 소요
    2. **실시간 협업 기능** - 2주 소요
    """
    

    async def _update_notion_ai_block(self, filename: str, file_summary: str, user_id: str):
        """Notion AI 요약 블록 업데이트"""
        
        try:
            # 1. 해당 파일과 연관된 학습 페이지 찾기
            # (여기서는 간단히 구현, 실제로는 Supabase에서 조회)
            
            # 2. AI 요약 블록 ID 조회
            # ai_block_id = await get_ai_block_id_by_filename(filename, user_id)
            
            # 3. Notion API로 블록 업데이트
            # await notion_service.update_ai_summary_by_block(ai_block_id, file_summary)
            
            api_logger.info(f"파일 '{filename}' Notion 업데이트 완료")
            
        except Exception as e:
            api_logger.error(f"Notion 업데이트 실패: {str(e)}")

    async def _generate_architecture_suggestions(self, filename: str, file_summary: str, user_id: str):
        """아키텍처 개선 제안 생성 및 별도 저장"""
        
        # 개선 제안만 추출하는 LLM 호출
        suggestions_prompt = f"""
    파일명: {filename}
    다음 파일 분석 결과에서 **구체적이고 실행 가능한 개선 제안**만 추출해주세요:

    {file_summary}

    형식:
    ## 🚀 즉시 적용 가능 (1-2시간)
    - [ ] 구체적 개선사항 1
    - [ ] 구체적 개선사항 2

    ## 🔧 단기 개선 (1주 이내)  
    - [ ] 구체적 개선사항 3
    - [ ] 구체적 개선사항 4

    ## 💡 장기 개선 (1개월 이내)
    - [ ] 구체적 개선사항 5
    - [ ] 구체적 개선사항 6
    """
        
        suggestions = await self._call_llm_for_file_analysis(suggestions_prompt)
        
        # Redis에 개선 제안 별도 저장
        suggestions_key = f"suggestions:{filename}"
        self.redis_client.setex(suggestions_key, 86400 * 7, suggestions)  # 7일 보관
        
        api_logger.info(f"파일 '{filename}' 개선 제안 생성 완료")