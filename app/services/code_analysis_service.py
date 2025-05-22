from redis import Redis
from supabase._async.client import AsyncClient
from typing import Dict, List, Any, Tuple, Optional
from app.utils.logger import api_logger
import asyncio
import re
import json
import time

class CodeAnalysisService:
    """코드 분석 및 LLM 처리를 담당하는 서비스"""
    def __init__(self, redis_client: Redis, supabase: AsyncClient):
        self.redis_client = redis_client
        self.supabase = supabase
        self.queue = asyncio.Queue()  # 비동기 큐
    
    async def analyze_code_changes(self, files: List[Dict], owner: str, repo: str, commit_sha: str, user_id: str):
        """코드 변경 분석 진입점"""
        api_logger.info(f"분석할 파일 수: {len(files)}")
        tasks = []
        processed_count = 0  # 처리된 파일 수

        for i, file in enumerate(files):
            # 패치 또는 전체 내용이 없으면 건너뛰기
            if "patch" not in file and "full_content" not in file:
                api_logger.info(f"파일 {i+1}/{len(files)} '{file.get('filename', 'unknown')}': 패치/내용 없음, 건너뜀")
                continue
                
            # 전체 파일 내용이 있으면 우선 사용, 없으면 패치 사용
            if "full_content" in file:
                # 전체 파일 내용 사용
                code_to_analyze = file["full_content"]
                
                # 패치 정보가 있으면 변경 라인 번호 추출
                changed_lines = []
                if "patch" in file:
                    changed_lines = self._extract_changed_lines(file["patch"])
                    api_logger.info(f"파일 '{file['filename']}' 변경 라인 추출: {len(changed_lines)} 라인")
                
                api_logger.info(f"파일 '{file['filename']}' 전체 내용 분석 (길이: {len(code_to_analyze)})")
                
                # 변경된 라인을 함수/클래스 단위로 매핑
                code_blocks = self._map_changes_to_functions(code_to_analyze, file["filename"], changed_lines)
                
            else:
                # 패치에서 실제 코드만 추출 (이전 방식)
                code_to_analyze, changed_lines = self._parse_patch(file["patch"])
                api_logger.info(f"파일 '{file['filename']}' 패치 내용 분석 (패치 길이: {len(file['patch'])}, 추출 코드 길이: {len(code_to_analyze)})")
                code_blocks = [{"code": code_to_analyze, "type": "patch_only"}]
               
            processed_count += 1
            
            # 각 코드 블록에 대해 분석 작업 등록
            for block in code_blocks:
                tasks.append(self._enqueue_code_analysis(
                    block["code"], 
                    file["filename"],
                    commit_sha, 
                    user_id,
                    block.get("metadata", {})
                ))
        
        api_logger.info(f"총 {len(files)}개 파일 중 {processed_count}개 파일 분석 작업 등록됨")
        if tasks:
            await asyncio.gather(*tasks)
            api_logger.info("모든 코드 분석 작업이 큐에 추가됨")
        else:
            api_logger.warning("분석할 파일이 없습니다 - 큐에 작업이 추가되지 않음")
    
    def _extract_changed_lines(self, patch: str) -> List[int]:
        """
        diff 패치에서 변경된 라인 번호 추출
        @@ -a,b +c,d @@ 형식의 헤더에서 +c,d 부분 분석하여 변경된 라인 번호 목록 반환
        """
        changed_lines = []
        current_line = 0
        
        for line in patch.splitlines():
            # @@ -a,b +c,d @@ 형식 찾기
            hunk_header = re.match(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', line)
            if hunk_header:
                # 새 파일에서의 시작 라인 번호
                current_line = int(hunk_header.group(1))
                continue
                
            # 추가된 라인(+로 시작)이나 변경된 라인(+나 - 없는 문맥 라인)
            if line.startswith('+'):
                changed_lines.append(current_line)
                current_line += 1
            elif not line.startswith('-'):  # 문맥 라인(변경 없음)
                current_line += 1
                
        return changed_lines
    
    def _parse_patch(self, patch: str) -> Tuple[str, List[int]]:
        """
        패치 내용 파싱: 코드와 변경 라인 번호 동시에 추출
        
        1) 메타줄 (diff/index/---/+++/@@) 제거
        2) + / - 접두어 제거
        3) 앞뒤 공백·탭 제거
        4) 변경 라인 번호 추출
        
        Returns:
            Tuple[str, List[int]]: (정제된 코드, 변경된 라인 번호 목록)
        """
        cleaned = []
        changed_lines = []
        current_line = 0
        
        for line in patch.splitlines():
            # @@ -a,b +c,d @@ 형식 찾기
            hunk_header = re.match(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@', line)
            if hunk_header:
                # 새 파일에서의 시작 라인 번호
                current_line = int(hunk_header.group(1))
                continue
                
            # 메타 줄 건너뛰기
            if line.startswith(("diff ", "index ", "--- ", "+++ ")):
                continue
                
            # 삭제된 라인(-로 시작)은 건너뛰기
            if line.startswith('-'):
                continue
                
            # 추가된 라인(+로 시작)
            if line.startswith('+'):
                cleaned_line = line[1:].strip()
                if cleaned_line:  # 빈 줄 아닌 경우만 추가
                    cleaned.append(cleaned_line)
                    changed_lines.append(current_line)
                current_line += 1
            else:  # 문맥 라인(변경 없음)
                cleaned_line = line.strip()
                if cleaned_line:  # 빈 줄 아닌 경우만 추가
                    cleaned.append(cleaned_line)
                current_line += 1
                
        return "\n".join(cleaned), changed_lines
        
    def _map_changes_to_functions(self, file_content: str, filename: str, changed_lines: List[int]) -> List[Dict]:
        """
        변경된 라인을 함수/클래스 단위로 매핑
        
        Args:
            file_content: 파일 전체 내용
            filename: 파일 이름
            changed_lines: 변경된 라인 번호 목록
            
        Returns:
            List[Dict]: 변경이 포함된 코드 블록 목록 (함수/클래스 단위)
        """
        if not changed_lines:
            # 변경 라인이 없으면 전체 파일을 하나의 블록으로 처리
            return [{"code": file_content, "type": "full_file"}]
            
        # 파일 확장자 확인
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        
        # Python 파일인 경우 AST 파서 사용
        if ext == 'py':
            return self._parse_python_file(file_content, changed_lines)
        
        # 다른 언어는 정규식 기반 파싱 사용
        return self._parse_code_with_regex(file_content, changed_lines, ext)
    
    def _parse_python_file(self, file_content: str, changed_lines: List[int]) -> List[Dict]:
        """
        Python 파일을 AST를 사용하여 파싱하고 변경된 함수/클래스 추출
        
        Args:
            file_content: 파일 전체 내용
            changed_lines: 변경된 라인 번호 목록
            
        Returns:
            List[Dict]: 변경이 포함된 코드 블록 목록 (함수/클래스 단위)
        """
        import ast
        
        try:
            # 파일 내용 파싱
            tree = ast.parse(file_content)
            
            # 코드 블록 (함수/클래스) 추출
            blocks = []
            
            # 전체 라인 리스트
            lines = file_content.splitlines()
            
            # 전역 코드 블록 (임포트, 상수 등)
            global_lines = []
            global_changed = False
            
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    # 함수/클래스 정의 추출
                    start_line = node.lineno
                    end_line = 0
                    
                    # 종료 라인 찾기
                    for child in ast.walk(node):
                        if hasattr(child, 'lineno'):
                            end_line = max(end_line, getattr(child, 'end_lineno', child.lineno))
                    
                    # 함수/클래스에 변경된 라인이 포함되는지 확인
                    has_changes = any(start_line <= line <= end_line for line in changed_lines)
                    
                    if has_changes:
                        # 코드 블록 추출
                        block_code = '\n'.join(lines[start_line-1:end_line])
                        
                        # 메타데이터 준비
                        metadata = {
                            'type': 'class' if isinstance(node, ast.ClassDef) else 'function',
                            'name': node.name,
                            'start_line': start_line,
                            'end_line': end_line,
                            'changed_lines': [line for line in changed_lines if start_line <= line <= end_line]
                        }
                        
                        blocks.append({
                            'code': block_code,
                            'type': metadata['type'],
                            'metadata': metadata
                        })
                        
                    # 전역 영역에서 제외할 라인 표시
                    for i in range(start_line-1, end_line):
                        if i < len(lines):
                            global_lines.append(i)
            
            # 변경된 전역 코드 확인 (함수/클래스 외부)
            global_changed_lines = [line for line in changed_lines if line-1 not in global_lines and line-1 < len(lines)]
            
            if global_changed_lines:
                # 전역 코드 추출 (임포트 등)
                global_code = []
                for i, line in enumerate(lines):
                    if i not in global_lines:
                        global_code.append(line)
                        if i+1 in changed_lines:
                            global_changed = True
                
                if global_changed:
                    blocks.insert(0, {
                        'code': '\n'.join(global_code),
                        'type': 'global',
                        'metadata': {
                            'type': 'global',
                            'name': 'imports_and_globals',
                            'changed_lines': global_changed_lines
                        }
                    })
            
            # 변경된 블록이 없으면 전체 파일을 반환
            if not blocks:
                return [{"code": file_content, "type": "full_file"}]
                
            return blocks
            
        except SyntaxError as e:
            # 파싱 에러 발생 시 전체 파일을 하나의 블록으로 처리
            api_logger.error(f"Python 파일 파싱 에러: {str(e)}")
            return [{"code": file_content, "type": "full_file"}]
    
    def _parse_code_with_regex(self, file_content: str, changed_lines: List[int], ext: str) -> List[Dict]:
        """
        정규식을 사용하여 코드 블록 추출 및 변경 라인 매핑
        
        Args:
            file_content: 파일 전체 내용
            changed_lines: 변경된 라인 번호 목록
            ext: 파일 확장자
            
        Returns:
            List[Dict]: 변경이 포함된 코드 블록 목록
        """
        # 언어별 패턴 매핑
        lang_patterns = {
            # JavaScript/TypeScript
            'js': [
                # 함수 (화살표 함수 포함)
                r'(?:async\s+)?(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>))[^{]*\{(?:[^{}]|(?R))*\}',
                # 클래스
                r'class\s+(\w+)[^{]*\{(?:[^{}]|(?R))*\}'
            ],
            'ts': [
                # 함수 (화살표 함수 포함)
                r'(?:async\s+)?(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>))[^{]*\{(?:[^{}]|(?R))*\}',
                # 클래스
                r'class\s+(\w+)[^{]*\{(?:[^{}]|(?R))*\}'
            ],
            # Java
            'java': [
                # 메서드
                r'(?:public|private|protected|static|final|native|synchronized|abstract|transient)\s+[\w\<\>\[\]]+\s+(\w+)\([^\)]*\)(?:\s+throws\s+[\w\s,]+)?\s*\{(?:[^{}]|(?R))*\}',
                # 클래스
                r'(?:public|private|protected|static|final|abstract)\s+class\s+(\w+)[^{]*\{(?:[^{}]|(?R))*\}'
            ],
            # 기본 C 스타일 언어 패턴
            'default': [
                # 함수
                r'\w+\s+(\w+)\s*\([^)]*\)\s*\{(?:[^{}]|(?R))*\}',
                # 클래스/구조체
                r'(?:class|struct)\s+(\w+)[^{]*\{(?:[^{}]|(?R))*\}'
            ]
        }
        
        # 파일 타입에 맞는 패턴 선택
        patterns = lang_patterns.get(ext, lang_patterns['default'])
        
        # 전체 라인 리스트
        lines = file_content.splitlines()
        
        # 코드 블록 추출
        blocks = []
        matched_lines = set()
        
        for pattern in patterns:
            for match in re.finditer(pattern, file_content, re.DOTALL):
                # 블록 위치 계산
                block_text = match.group(0)
                block_start = file_content[:match.start()].count('\n') + 1
                block_end = block_start + block_text.count('\n')
                
                # 블록 이름 추출 (첫 번째 캡처 그룹)
                name = next((g for g in match.groups() if g), "unnamed")
                
                # 블록에 변경된 라인이 포함되는지 확인
                block_changed_lines = [line for line in changed_lines if block_start <= line <= block_end]
                
                if block_changed_lines:
                    # 블록 코드 추출
                    block_code = '\n'.join(lines[block_start-1:block_end])
                    
                    # 메타데이터 준비
                    block_type = 'class' if re.search(r'(class|struct|interface)', block_text[:50]) else 'function'
                    metadata = {
                        'type': block_type,
                        'name': name,
                        'start_line': block_start,
                        'end_line': block_end,
                        'changed_lines': block_changed_lines
                    }
                    
                    blocks.append({
                        'code': block_code,
                        'type': block_type,
                        'metadata': metadata
                    })
                    
                    # 매칭된 라인 기록
                    matched_lines.update(range(block_start, block_end + 1))
        
        # 매칭되지 않은 라인 중 변경된 라인이 있는지 확인
        unmatched_changed_lines = [line for line in changed_lines if line not in matched_lines]
        
        if unmatched_changed_lines:
            # 변경된 라인 주변 컨텍스트 추출 (앞뒤 10줄)
            context_blocks = []
            
            for line in unmatched_changed_lines:
                if line < 1 or line > len(lines):
                    continue
                    
                start = max(1, line - 10)
                end = min(len(lines), line + 10)
                
                # 이미 추가된 블록과 겹치는지 확인
                overlap = False
                for block in context_blocks:
                    if block['start'] <= line <= block['end']:
                        overlap = True
                        break
                
                if not overlap:
                    context_blocks.append({
                        'code': '\n'.join(lines[start-1:end]),
                        'type': 'context',
                        'start': start,
                        'end': end,
                        'metadata': {
                            'type': 'context',
                            'name': f'context_around_line_{line}',
                            'start_line': start,
                            'end_line': end,
                            'changed_lines': [l for l in unmatched_changed_lines if start <= l <= end]
                        }
                    })
            
            blocks.extend(context_blocks)
        
        # 변경된 블록이 없으면 전체 파일을 반환
        if not blocks:
            return [{"code": file_content, "type": "full_file"}]
            
        return blocks
    
    def _split_code_if_needed(self, code: str) -> List[str]:
        """코드가 너무 길면 여러 청크로 분할
        
        1. 함수/클래스 단위로 분할
        2. 개별 함수/클래스가 길면 여러 청크로 재분할
        3. 청크 간 연속성을 위한 메타데이터 포함
        """
        max_length = 3000  # 청크 최대 길이
        
        if len(code) <= max_length:
            return [code]
            
        # 코드 블록(함수/클래스) 패턴 (다중 언어 지원)
        # Python, JavaScript, TypeScript, Java, C#, C++, PHP 등 대부분의 언어에서 작동
        block_patterns = [
            # 함수 패턴 (def, function, public/private void 등)
            r'((?:def|function|async function|public|private|protected|static|void|int|string|bool|final)\s+\w+\s*\([^)]*\)\s*(?:\{|:)(?:.|\n)*?)(?=\n\s*(?:def|function|class|public|private|protected|static|void|int|string|bool|final)\s+|\Z)',
            # 클래스 패턴
            r'((?:class|interface|abstract class|struct)\s+\w+(?:\s+(?:extends|implements)\s+[^{]+)?\s*\{(?:.|\n)*?)(?=\n\s*(?:def|function|class|interface|abstract|public|private)\s+|\Z)'
        ]
        
        # 코드 블록 추출
        blocks = []
        remaining_code = code
        
        for pattern in block_patterns:
            matches = re.finditer(pattern, remaining_code, re.MULTILINE)
            for match in matches:
                blocks.append({
                    'code': match.group(0),
                    'start': match.start(),
                    'end': match.end(),
                    'type': 'function' if not match.group(0).strip().startswith(('class', 'interface', 'abstract class', 'struct')) else 'class'
                })
        
        # 시작 위치에 따라 블록 정렬
        blocks.sort(key=lambda x: x['start'])
        
        # 함수/클래스로 매칭되지 않은 코드 처리 (임포트, 주석, 전역 변수 등)
        if not blocks:
            # 매칭된 블록이 없으면 단순 길이 기반 분할
            return [code[i:i+max_length] for i in range(0, len(code), max_length)]
        
        # 블록 사이의 코드도 포함시키기
        complete_blocks = []
        last_end = 0
        
        for block in blocks:
            if block['start'] > last_end:
                # 블록 사이의 코드가 있으면 별도 블록으로 추가
                complete_blocks.append({
                    'code': remaining_code[last_end:block['start']],
                    'type': 'other'
                })
            complete_blocks.append(block)
            last_end = block['end']
        
        # 마지막 블록 이후 코드가 있으면 추가
        if last_end < len(remaining_code):
            complete_blocks.append({
                'code': remaining_code[last_end:],
                'type': 'other'
            })
        
        # 각 블록을 적절한 크기로 분할하고 메타데이터 추가
        chunks = []
        for block in complete_blocks:
            block_code = block['code']
            
            # 블록이 max_length보다 작으면 바로 추가
            if len(block_code) <= max_length:
                chunks.append(block_code)
                continue
            
            # 블록 이름 추출 (함수/클래스명)
            block_name = "unknown"
            if block['type'] in ['function', 'class']:
                name_match = re.search(r'(?:def|function|class|interface|public|private|protected|static|void|int|string|bool)\s+(\w+)', block_code)
                if name_match:
                    block_name = name_match.group(1)
            
            # 블록을 여러 청크로 분할
            block_chunks = []
            for i in range(0, len(block_code), max_length):
                chunk = block_code[i:i+max_length]
                
                # 첫 번째 청크가 아니면 이전 청크와의 연결성을 위한 메타데이터 추가
                if i > 0:
                    # 이전 청크 요약 참조를 위한 주석 추가
                    summary_reference = f"# {block['type']} {block_name}[청크 {i//max_length}] - 이전 청크에서 계속됨\n"
                    chunk = summary_reference + chunk
                
                # 마지막 청크가 아니면 계속된다는 표시 추가
                if i + max_length < len(block_code):
                    continuation_note = f"\n# {block['type']} {block_name} - 다음 청크에서 계속됨"
                    chunk = chunk + continuation_note
                
                block_chunks.append(chunk)
            
            chunks.extend(block_chunks)
        
        return chunks
    
    async def _enqueue_code_analysis(self, code: str, filename: str, commit_sha: str, user_id: str, metadata: Dict = {}):
        """코드 분석 작업을 큐에 넣음"""
        # 코드가 길면 적절히 분할
        api_logger.info(f"'{filename}' 코드 분할 시작 (길이: {len(code)})")
        chunks = self._split_code_if_needed(code)
        api_logger.info(f"'{filename}' 분할 결과: {len(chunks)}개 청크")
        
        # 메타데이터에서 기존 청크 정보 추출
        existing_metadata = metadata.copy()
        
        for i, chunk in enumerate(chunks):
            # 청크별 메타데이터 생성
            chunk_metadata = existing_metadata.copy()
            
            # 각 청크에서 추가 메타데이터 추출 (주석 기반)
            extracted_metadata = self._extract_metadata(chunk)
            chunk_metadata.update(extracted_metadata)
            
            # 여러 청크로 분할된 경우 연속성 메타데이터 추가
            if len(chunks) > 1:
                if i > 0:  # 첫 번째 청크가 아니면
                    chunk_metadata['is_continuation'] = True
                    chunk_metadata['previous_chunk'] = i - 1
                
                if i < len(chunks) - 1:  # 마지막 청크가 아니면
                    chunk_metadata['has_next_chunk'] = True
                    chunk_metadata['next_chunk'] = i + 1
            
            await self.queue.put({
                "code": chunk,
                "metadata": chunk_metadata,
                "filename": filename,
                "commit_sha": commit_sha,
                "user_id": user_id,
                "chunk_index": i,
                "total_chunks": len(chunks)
            })
            api_logger.info(f"'{filename}' 청크 {i+1}/{len(chunks)} 큐에 추가됨 (길이: {len(chunk)})")
    
    async def process_queue(self):
        """큐에 쌓인 코드 분석 작업을 모두 처리하고 종료"""
        api_logger.info("코드 분석 큐 처리 시작")
        while not self.queue.empty():
            try:
                item = await self.queue.get()
                await self._process_code_analysis(item)
                self.queue.task_done()
            except Exception as e:
                api_logger.error(f"큐 처리 중 오류 발생: {str(e)}")
                continue
        api_logger.info("모든 큐 항목 처리 완료")
    
    async def _process_code_analysis(self, item: Dict):
        """개별 코드 분석 항목 처리"""
        try:
            # 참조 파일 가져오기 (있을 경우)
            await self._fetch_reference_files(item)
            
            # 코드 분석 요청 준비
            code = item['code']
            filename = item['filename']
            metadata = item.get('metadata', {})
            chunk_index = item.get('chunk_index', 0)
            total_chunks = item.get('total_chunks', 1)
            
            # 파일 확장자 추출
            ext = filename.split('.')[-1].lower() if '.' in filename else ''
            
            # 프롬프트 구성
            system_prompt = f"""다음 코드 청크를 분석하고 요약해주세요.
파일명: {filename}
청크: {chunk_index + 1}/{total_chunks}

요약 지침:
1. 코드의 목적과 기능을 명확히 설명하세요.
2. 주요 클래스, 함수, 변수의 역할을 설명하세요.
3. 로직 흐름을 간략히 설명하세요.
4. 에러 처리나 중요한 예외 상황을 언급하세요.

"""
            
            # 메타데이터에 따른 추가 프롬프트
            if 'type' in metadata:
                if metadata['type'] == 'function':
                    system_prompt += f"\n이 코드는 '{metadata['name']}' 함수를 포함하고 있습니다."
                elif metadata['type'] == 'class':
                    system_prompt += f"\n이 코드는 '{metadata['name']}' 클래스를 포함하고 있습니다."
                elif metadata['type'] == 'global':
                    system_prompt += "\n이 코드는 전역 영역(임포트, 상수 정의 등)을 포함하고 있습니다."
            
            if 'changed_lines' in metadata and metadata['changed_lines']:
                lines = code.splitlines()
                changed_lines_text = "\n\n변경된 라인:\n"
                
                for line_num in metadata['changed_lines']:
                    if 0 <= line_num - metadata.get('start_line', 1) < len(lines):
                        line_idx = line_num - metadata.get('start_line', 1)
                        if line_idx < len(lines):
                            changed_lines_text += f"{line_num}: {lines[line_idx]}\n"
                
                system_prompt += changed_lines_text
                system_prompt += "\n특히 위의 변경된 라인의 목적과 영향에 초점을 맞추어 설명해주세요."
            
            # 참조 파일 정보 추가
            if 'reference_content' in metadata:
                system_prompt += f"\n\n참조 파일({metadata['reference_file']})을 고려하여 분석하세요."
            
            api_logger.info(f"'{filename}' 청크 {chunk_index+1}/{total_chunks} 처리 시작")
            
            # TODO: 실제 LLM 호출 구현
            # LLM 분석 결과
            analysis_result = "LLM 분석 결과가 여기에 들어갑니다."
            
            # 결과 저장
            await self._save_analysis_result(item, analysis_result)
            
            api_logger.info(f"'{filename}' 청크 {chunk_index+1}/{total_chunks} 처리 완료")
            
        except Exception as e:
            api_logger.error(f"코드 분석 처리 중 오류: {str(e)}")
    
    def _extract_metadata(self, code: str) -> Dict[str, Any]:
        """코드 청크에서 메타데이터 추출"""
        metadata = {}
        
        # 주석에서 메타데이터 추출 로직
        lines = code.split('\n')
        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith('#'):
                # 청크 연속성 메타데이터 처리
                chunk_continuation = re.search(r'(function|class)\s+(\w+)\[청크\s+(\d+)\]\s*-\s*이전\s+청크에서\s+계속됨', line)
                if chunk_continuation:
                    block_type = chunk_continuation.group(1)
                    block_name = chunk_continuation.group(2)
                    chunk_index = int(chunk_continuation.group(3))
                    metadata['is_continuation'] = True
                    metadata['block_type'] = block_type
                    metadata['block_name'] = block_name
                    metadata['previous_chunk'] = chunk_index - 1
                    # 첫 번째 주석이 연속성 표시면 다음 주석으로 넘어감
                    continue
                
                # 다음 청크로 계속됨 표시 처리
                next_chunk = re.search(r'(function|class)\s+(\w+)\s*-\s*다음\s+청크에서\s+계속됨', line)
                if next_chunk:
                    block_type = next_chunk.group(1)
                    block_name = next_chunk.group(2)
                    metadata['has_next_chunk'] = True
                    metadata['block_type'] = block_type
                    metadata['block_name'] = block_name
                    continue
                
                # [파일경로] 형식 추출
                if '[' in line and ']' in line:
                    match = re.search(r'\[(.*?)\]', line)
                    if match:
                        metadata['reference_file'] = match.group(1)
                
                # {응답 형식} 형식 추출
                if '{' in line and '}' in line:
                    match = re.search(r'\{(.*?)\}', line)
                    if match:
                        metadata['response_format'] = match.group(1)
                
                # (요구사항) 형식 추출
                if '(' in line and ')' in line:
                    match = re.search(r'\((.*?)\)', line)
                    if match:
                        metadata['requirements'] = match.group(1)
                
                # 일반 주석 텍스트
                metadata['comment'] = line.lstrip('#').strip()
                # 첫 번째 일반 주석만 처리하고 중단 (연속성 표시는 제외)
                break
        
        return metadata
    
    async def _save_analysis_result(self, item: Dict, analysis_result: str):
        """분석 결과 저장"""
        try:
            # 분석 결과 메타데이터
            result_data = {
                "user_id": item["user_id"],
                "commit_sha": item["commit_sha"],
                "filename": item["filename"],
                "chunk_index": item.get("chunk_index", 0),
                "total_chunks": item.get("total_chunks", 1),
                "analysis": analysis_result,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # 메타데이터에서 중요 정보 추출
            metadata = item.get("metadata", {})
            if "type" in metadata:
                result_data["block_type"] = metadata["type"]
            if "name" in metadata:
                result_data["block_name"] = metadata["name"]
            if "changed_lines" in metadata:
                result_data["changed_lines"] = metadata["changed_lines"]
            
            # Supabase에 저장
            result = await self.supabase.table("code_analysis_results").insert(result_data).execute()
            
            # Redis에도 캐싱
            cache_key = f"analysis:{item['user_id']}:{item['commit_sha']}:{item['filename']}:{item.get('chunk_index', 0)}"
            self.redis_client.setex(cache_key, 86400, json.dumps(result_data))  # 24시간 유지
            
            api_logger.info(f"분석 결과 저장 완료: {item['filename']} 청크 {item.get('chunk_index', 0)+1}/{item.get('total_chunks', 1)}")
            
        except Exception as e:
            api_logger.error(f"분석 결과 저장 실패: {str(e)}")
    
    async def _fetch_reference_files(self, item: Dict):
        """메타데이터에서 참조 파일 정보 추출 및 가져오기"""
        metadata = item.get('metadata', {})
        
        # 참조 파일 정보가 없으면 처리 필요 없음
        if 'reference_file' not in metadata:
            return
            
        # Redis에서 이미 가져온 참조 파일인지 확인
        reference_path = metadata['reference_file']
        user_id = item['user_id']
        commit_sha = item['commit_sha']
        
        cache_key = f"{user_id}:ref:{reference_path}:{commit_sha}"
        cached_content = self.redis_client.get(cache_key)
        
        if cached_content:
            # 캐시에서 참조 파일 내용 가져오기
            metadata['reference_content'] = cached_content
            api_logger.info(f"참조 파일 '{reference_path}' 캐시에서 로드됨")
            return
            
        try:
            # Redis 키-값 방식으로 참조 파일 요청
            # owner/repo 정보 추출 시도
            owner_repo = None
            if '/' in reference_path:
                parts = reference_path.split('/')
                if len(parts) >= 2:
                    # 경로에서 owner/repo 부분 추출 시도
                    owner_repo = '/'.join(parts[:2])
            
            # 고유한 요청 ID 생성
            request_id = f"{user_id}_{commit_sha}_{int(time.time())}_{item['chunk_index']}"
            
            # 참조 파일 요청 데이터 구성
            request_data = {
                'path': reference_path,
                'commit_sha': commit_sha,
                'request_id': request_id
            }
            
            # 요청 키 설정
            owner_repo = owner_repo or "unknown"
            request_key = f"ref_request:{owner_repo}:{user_id}:{request_id}"
            response_key = f"ref_response:{owner_repo}:{user_id}:{request_id}"
            
            # 요청 저장 (5분 유효)
            self.redis_client.setex(request_key, 300, json.dumps(request_data))
            api_logger.info(f"참조 파일 '{reference_path}' 요청 등록됨 (ID: {request_id})")
            
            # 응답 폴링 (최대 5초)
            MAX_WAIT_TIME = 5.0  # 5초
            start_time = time.time()
            
            while time.time() - start_time < MAX_WAIT_TIME:
                # 응답 확인
                response_data_str = self.redis_client.get(response_key)
                if response_data_str:
                    response_data = json.loads(response_data_str)
                    if response_data.get('status') == 'success':
                        file_content = response_data.get('content', '')
                        metadata['reference_content'] = file_content
                        
                        # Redis에 참조 파일 내용 캐싱
                        self.redis_client.setex(cache_key, 86400, file_content)  # 24시간 유지
                        api_logger.info(f"참조 파일 '{reference_path}' 로드 성공")
                        break
                    elif response_data.get('status') == 'error':
                        metadata['reference_error'] = response_data.get('error', '알 수 없는 오류')
                        api_logger.error(f"참조 파일 오류: {metadata['reference_error']}")
                        break
                
                # 잠시 대기 후 다시 확인
                await asyncio.sleep(0.5)
                
            # 타임아웃 체크
            if 'reference_content' not in metadata and 'reference_error' not in metadata:
                metadata['reference_error'] = '참조 파일 요청 타임아웃'
                api_logger.error(f"참조 파일 '{reference_path}' 요청 타임아웃")
                    
        except Exception as e:
            api_logger.error(f"참조 파일 '{reference_path}' 처리 실패: {str(e)}")
            metadata['reference_error'] = str(e)