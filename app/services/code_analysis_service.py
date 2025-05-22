
from redis import Redis
from supabase._async.client import AsyncClient
from typing import Dict, List, Any, Tuple, Optional
from app.utils.logger import api_logger
import asyncio
import re
import json
import time
import ast
import hashlib

class CodeAnalysisService:
    """함수 중심 코드 분석 및 LLM 처리 서비스"""
    def __init__(self, redis_client: Redis, supabase: AsyncClient):
        self.redis_client = redis_client
        self.supabase = supabase
        self.function_queue = asyncio.Queue()  # 함수별 분석 큐
    
    async def analyze_code_changes(self, files: List[Dict], owner: str, repo: str, commit_sha: str, user_id: str):
        """코드 변경 분석 진입점 - 함수 중심으로 재설계"""
        api_logger.info(f"함수별 분석 시작: {len(files)}개 파일")
        
        for file in files:
            filename = file.get('filename', 'unknown')
            
            if "patch" not in file and "full_content" not in file:
                api_logger.info(f"파일 '{filename}': 분석할 내용 없음, 건너뜀")
                continue
            
            # 전체 파일 내용과 변경 정보 추출
            if "full_content" in file:
                file_content = file["full_content"]
                diff_info = self._extract_detailed_diff(file.get("patch", "")) if "patch" in file else {}
            else:
                file_content, diff_info = self._parse_patch_with_context(file["patch"])
            
            # 파일을 함수 단위로 분해
            functions = await self._extract_functions_from_file(file_content, filename, diff_info)
            
            # 각 함수를 분석 큐에 추가
            for func_info in functions:
                await self._enqueue_function_analysis(func_info, commit_sha, user_id, owner, repo)
            
            api_logger.info(f"파일 '{filename}': {len(functions)}개 함수 분석 큐에 추가")
    
    def _extract_detailed_diff(self, patch: str) -> Dict[int, Dict]:
        """diff 패치에서 상세 변경 정보 추출"""
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
        """패치에서 코드와 변경 정보 동시 추출"""
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
    
    async def _enqueue_function_analysis(self, func_info: Dict, commit_sha: str, user_id: str, owner: str, repo: str):
        """함수별 분석 작업을 큐에 추가"""
        # 메타데이터에서 참조 정보 추출
        metadata = self._extract_function_metadata(func_info['code'])
        
        analysis_item = {
            'function_info': func_info,
            'commit_sha': commit_sha,
            'user_id': user_id,
            'owner': owner,
            'repo': repo,
            'metadata': metadata
        }
        
        await self.function_queue.put(analysis_item)
        api_logger.info(f"함수 '{func_info['name']}' 분석 큐에 추가됨")
    
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
        """개별 함수 분석 처리"""
        func_info = item['function_info']
        func_name = func_info['name']
        filename = func_info['filename']
        user_id = item['user_id']
        
        api_logger.info(f"함수 '{func_name}' 분석 시작")
        
        # Redis에서 이전 분석 결과 조회
        redis_key = f"func:{filename}:{func_name}"
        previous_summary = self.redis_client.get(redis_key)
        
        # 참조 파일 내용 가져오기
        reference_content = None
        if 'reference_file' in item['metadata']:
            reference_content = await self._fetch_reference_function(
                item['metadata']['reference_file'], 
                item['owner'], 
                item['repo'], 
                item['commit_sha']
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
                reference_content
            )
        else:
            # 다중 청크 연속 처리
            summary = await self._process_multi_chunk_function(
                func_info, 
                chunks, 
                item['metadata'], 
                previous_summary, 
                reference_content
            )
        
        # Redis에 최종 요약 저장
        self.redis_client.setex(redis_key, 86400 * 7, summary)  # 7일 보관
        
        # Notion 업데이트는 파일 단위로 별도 처리
        await self._update_notion_if_needed(func_info, summary, user_id)
        
        api_logger.info(f"함수 '{func_name}' 분석 완료")
    
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
                                          reference_content: str) -> str:
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
                chunk_index=i,
                total_chunks=len(chunks)
            )
            
            current_summary = chunk_summary  # 다음 청크에서 사용할 요약 업데이트
        
        return current_summary
    
    async def _call_llm_for_function(self, func_info: Dict, code: str, metadata: Dict, 
                                   previous_summary: str = None, reference_content: str = None,
                                   chunk_index: int = 0, total_chunks: int = 1) -> str:
        """함수별 LLM 분석 호출"""
        
        # 프롬프트 구성
        prompt_parts = []
        
        # 기본 시스템 프롬프트
        if total_chunks > 1:
            prompt_parts.append(f"다음은 '{func_info['name']}' 함수의 {chunk_index+1}/{total_chunks} 청크입니다.")
        else:
            prompt_parts.append(f"다음은 '{func_info['name']}' 함수의 코드입니다.")
        
        # 이전 요약이 있으면 포함
        if previous_summary:
            prompt_parts.append(f"\n이전 분석 결과:\n{previous_summary}")
            if total_chunks > 1:
                prompt_parts.append("\n위 분석을 바탕으로 다음 코드 청크를 분석하고 통합된 요약을 제공하세요.")
            else:
                prompt_parts.append("\n위 분석을 참고하여 변경사항을 중심으로 업데이트된 분석을 제공하세요.")
        
        # 참조 파일 내용 포함
        if reference_content:
            prompt_parts.append(f"\n참조 함수 코드:\n{reference_content}")
        
        # 메타데이터 기반 커스텀 프롬프트
        if 'custom_prompt' in metadata:
            prompt_parts.append(f"\n추가 요구사항: {metadata['custom_prompt']}")
        
        if 'return_type' in metadata:
            prompt_parts.append(f"\n예상 반환 타입: {metadata['return_type']}")
        
        if 'requirements' in metadata:
            prompt_parts.append(f"\n구현 요구사항: {metadata['requirements']}")
        
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
                prompt_parts.append(f"\n🔥 주요 변경사항:\n" + "\n".join(changes_text))
                prompt_parts.append("\n특히 위 변경사항의 목적과 영향을 중점적으로 분석해주세요.")
        
        # 분석할 코드
        prompt_parts.append(f"\n분석할 코드:\n```{func_info.get('filename', '').split('.')[-1]}\n{code}\n```")
        
        # 응답 형식 지정
        prompt_parts.append("""
분석 결과를 다음 형식으로 제공하세요:
1. **기능 요약**: 함수의 핵심 목적을 한 문장으로
2. **주요 로직**: 핵심 알고리즘이나 처리 흐름
3. **변경 영향**: (변경사항이 있는 경우) 변경으로 인한 동작 변화
4. **의존성**: 사용하는 외부 함수나 라이브러리
5. **개선 제안**: (필요시) 코드 품질 향상 방안
""")
        
        full_prompt = "\n".join(prompt_parts)
        
        # TODO: 실제 LLM API 호출 구현
        # OpenAI API 호출 예시:
        # response = await openai.ChatCompletion.acreate(
        #     model="gpt-4",
        #     messages=[{"role": "user", "content": full_prompt}],
        #     temperature=0.3
        # )
        # return response.choices[0].message.content
        
        # 임시 응답
        return f"[LLM 분석 결과] {func_info['name']} 함수: {func_info.get('type', 'function')} 타입"
    
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
    
    async def _update_notion_if_needed(self, func_info: Dict, summary: str, user_id: str):
        """필요시 Notion 페이지 업데이트"""
        # 파일 단위로 통합된 요약을 Notion에 저장하는 로직
        # 실제 구현에서는 파일별로 모든 함수 분석이 완료된 후 실행
        pass