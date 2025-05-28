from redis import Redis
from supabase._async.client import AsyncClient
from typing import Dict, List, Any, Tuple, Optional
from app.utils.logger import api_logger
from datetime import date, datetime
import asyncio
import re
import json
import time
import sys
import os
from openai import OpenAI
from app.services.redis_service import RedisService
from app.services.extract_for_file_service import extract_functions_by_type
from app.services.notion_service import NotionService
from app.services.auth_service import get_integration_token
# 버퍼링 비활성화
os.environ["PYTHONUNBUFFERED"] = "1"

class CodeAnalysisService:
    """함수 중심 코드 분석 및 LLM 처리 서비스"""
    def __init__(self, redis_client: Redis, supabase: AsyncClient):
        self.redis_client = redis_client
        self.redis_service = RedisService()
        self.supabase = supabase
        self.function_queue = asyncio.Queue()
    
    async def analyze_code_changes(self, files: List[Dict], owner: str, repo: str, commit_sha: str, user_id: str):
        """코드 변경 분석 처리"""
        api_logger.info(f"함수별 분석 시작: {len(files)}개 파일")
        sys.stdout.flush()
        
        for file in files:
            filename = file.get('filename', 'unknown')
            status = file.get('status', '')
                        
            if "patch" not in file and "full_content" not in file:
                api_logger.info(f"파일 '{filename}': 분석할 내용 없음, 건너뜀")
                continue
            
            # 파일 내용 추출
            if "full_content" in file:
                file_content = file["full_content"]
                
                # full_content가 patch 형태인지 확인하고 파싱
                if (file_content.startswith('@@') or 
                    any(line.startswith(('+', '-', '@@')) for line in file_content.split('\n')[:5])):
                    file_content, _ = self._parse_patch_with_context(file_content)
            else:
                file_content, _ = self._parse_patch_with_context(file["patch"])
            
            # diff 정보 추출 (새 파일은 diff 분석 불필요)
            if status == "added":
                diff_info = {}
            elif "patch" in file or (file.get("full_content", "").startswith(('@@', '+', '-'))):
                # patch가 있거나 full_content가 patch 형태면 diff 추출
                patch_content = file.get("patch") or file.get("full_content", "")
                diff_info = self._extract_detailed_diff(patch_content)
            else:
                diff_info = {}
            
            # 파일을 함수 단위로 분해
            functions = await self._extract_functions_from_file(file_content, filename, diff_info)
            
            # 각 함수를 분석 큐에 추가
            for func_info in functions:
                # 새 파일 처리
                if status == "added":
                    func_info['has_changes'] = False  # 변경사항 아님
                    func_info['changes'] = {}
                    func_info['is_new_file'] = True   # 새 파일 플래그
                
                await self._enqueue_function_analysis(func_info, commit_sha, user_id, owner, repo)
            
            api_logger.info(f"파일 '{filename}': {len(functions)}개 함수중 {len([f for f in functions if f.get('has_changes', True) or f.get('is_new_file', False)])}개 변경된 함수 분석 큐에 추가")
            sys.stdout.flush()
    
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
        """파일에서 함수/메서드를 개별적으로 추출 (새로운 레지스트리 패턴 사용)"""
               
        return await extract_functions_by_type(file_content, filename, diff_info)
        
    async def _enqueue_function_analysis(self, func_info: Dict, commit_sha: str, user_id: str, owner: str, repo: str):
        """함수별 분석 작업을 큐에 추가 - 변경된 함수 + 새 파일"""
        
        # 변경사항도 없고 새 파일도 아니면 스킵
        if not func_info.get('has_changes', True) and not func_info.get('is_new_file', False): 
            api_logger.info(f"함수 '{func_info['name']}' 변경 없음")
            return
        
        # Redis 키 생성 (commit_sha 포함)
        redis_key = f"{user_id}:func:{commit_sha}:{func_info['filename']}:{func_info['name']}"
        cached_result = self.redis_client.get(redis_key)
        
        # 캐시가 있고 변경사항이 없는 기존 파일만 캐시 사용 (새 파일은 항상 분석)
        if cached_result and not func_info.get('has_changes', True) and not func_info.get('is_new_file', False):
            api_logger.info(f"함수 '{func_info['name']}' 변경 없음, 캐시 사용")
            return
        
        # 변경된 함수이거나 새 파일인 경우 큐에 추가
        if func_info.get('has_changes', True) or func_info.get('is_new_file', False):
            analysis_item = {
                'function_info': func_info,
                'commit_sha': commit_sha,
                'user_id': user_id,
                'owner': owner,
                'repo': repo,
                'metadata': self._extract_function_metadata(func_info['code'])
            }
            
            await self.function_queue.put(analysis_item)
            
            if func_info.get('is_new_file', False):
                api_logger.info(f"함수 '{func_info['name']}' 분석 큐에 추가됨 (새 파일)")
            else:
                api_logger.info(f"함수 '{func_info['name']}' 분석 큐에 추가됨 (변경 감지)")
    
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

                # 파일#함수 형식: #[파일경로#함수명]
                func_ref_match = re.search(r'\[([^#\]]+)#([^\]]+)\]', line)
                if func_ref_match:
                    metadata['reference_file'] = func_ref_match.group(1)
                    metadata['reference_function'] = func_ref_match.group(2)
                    break

                # 단순 참조 파일만 있는 경우: #[파일.py]
                ref_match = re.search(r'\[([^\]]+\.py)\]', line)
                if ref_match:
                    metadata['reference_file'] = ref_match.group(1)
        
        return metadata
    
    async def process_queue(self):
        """함수별 분석 큐 처리"""
        api_logger.info("함수별 분석 큐 처리 시작")
        sys.stdout.flush()
        
        while not self.function_queue.empty():
            item = None
            try:
                item = await self.function_queue.get()
                await self._analyze_function(item)
            except Exception as e:
                api_logger.error(f"함수 분석 처리 오류: {e}")
                # 오류 발생 시에도 실패한 함수 정보 로깅
                if item:
                    func_name = item.get('function_info', {}).get('name', 'unknown')
                    api_logger.error(f"실패한 함수: {func_name}")
            finally:
                # 성공/실패 관계없이 task_done() 호출
                if item:
                    self.function_queue.task_done()
        
        api_logger.info("모든 함수 분석 완료")
        sys.stdout.flush()
    
    async def _analyze_function(self, item: Dict):
        """개별 함수 분석 처리"""
        func_info = item['function_info']
        func_name = func_info['name']
        filename = func_info['filename']
        commit_sha = item['commit_sha']
        user_id = item['user_id']
        
        api_logger.info(f"함수 '{func_name}' 분석 시작")
        
        # Redis에서 이전 분석 결과 조회
        redis_key = f"{user_id}:func:{commit_sha}:{filename}:{func_name}"
        previous_summary = self.redis_client.get(redis_key)
        
        # 참조 파일 내용 가져오기
        reference_content = None
        if 'reference_file' in item['metadata']:
            # reference_function이 있으면 파일#함수 형식으로 조합
            if 'reference_function' in item['metadata']:
                reference_path = f"{item['metadata']['reference_file']}#{item['metadata']['reference_function']}"
            else:
                reference_path = item['metadata']['reference_file']
                
            reference_content = await self._fetch_reference_function(
                reference_path,
                item['owner'], 
                item['repo'], 
                item['commit_sha'],
                user_id
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
        
        # Redis에 최종 요약 저장 (str을 bytes로 인코딩)
        summary_bytes = summary.encode('utf-8') if isinstance(summary, str) else summary
        self.redis_client.setex(redis_key, 86400 * 7, summary_bytes)  # 7일 보관
        
        # Notion 업데이트는 파일 단위로 별도 처리
        await self._update_notion_if_needed(func_info, summary, user_id, commit_sha)
        
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
            sys.stdout.flush()
            
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
        
        # 임시 응답 반환 (실제 LLM 호출 대신)
        return f"[파싱 완료] {func_info['name']} 함수 분석 정보 로깅됨"
    
    async def _fetch_reference_function(self, reference_file: str, owner: str, repo: str, commit_sha: str, user_id: str) -> str:
        """참조 파일의 함수 요약을 Redis에서 조회"""
        # 파일에서 특정 함수가 지정되었는지 확인
        if '#' in reference_file:
            file_path, func_name = reference_file.split('#', 1)
            redis_key = f"{user_id}:func:{commit_sha}:{file_path}:{func_name}"
            cached_content = self.redis_client.get(redis_key)
            if cached_content:
                return cached_content
        else:
            # 파일 전체 참조인 경우 주요 함수들 조회
            pattern = f"{user_id}:func:{commit_sha}:{reference_file}:*"
            function_keys = self.redis_client.keys(pattern)
            
            if function_keys:
                # 여러 함수가 있으면 모두 조합
                all_summaries = []
                for key in function_keys:
                    # Redis key가 bytes일 수 있으므로 str로 변환
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                    func_name = key_str.split(":")[-1]
                    summary_raw = self.redis_client.get(key)
                    if summary_raw:
                        # bytes면 str로 변환, 이미 str이면 그대로 사용
                        summary = summary_raw.decode('utf-8') if isinstance(summary_raw, bytes) else summary_raw
                        all_summaries.append(f"**{func_name}():**\n{summary}")
                
                if all_summaries:
                    return "\n\n".join(all_summaries)
        
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
        
        # JSON 데이터를 bytes로 인코딩해서 저장
        request_data_json = json.dumps(request_data)
        request_data_bytes = request_data_json.encode('utf-8')
        self.redis_client.setex(request_key, 300, request_data_bytes)
        
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
        if await self._is_file_analysis_complete(filename, user_id):
            # 2. 파일별 종합 분석 수행
            file_summary = await self._generate_file_level_analysis(filename, user_id)
            
            # 3. Notion AI 요약 블록 업데이트
            await self._update_notion_ai_block(filename, file_summary, user_id, commit_sha)
            
            # 4. 아키텍처 개선 제안 생성
            await self._generate_architecture_suggestions(filename, file_summary, user_id)

    async def _is_file_analysis_complete(self, filename: str, user_id: str) -> bool:
        """파일의 모든 함수 분석이 완료되었는지 확인"""
        
        # Redis에서 해당 파일의 모든 함수 키 조회
        pattern = f"{user_id}:func:*:{filename}:*"
        function_keys = self.redis_client.keys(pattern)
        
        # 분석 대기 중인 함수가 있는지 큐에서 확인
        temp_queue = []
        pending_functions = set()
        
        # 큐에서 해당 파일의 대기 중인 함수들 확인
        try:
            while not self.function_queue.empty():
                item = await self.function_queue.get()
                temp_queue.append(item)
                
                if item and item.get('function_info', {}).get('filename') == filename:
                    func_name = item.get('function_info', {}).get('name', 'unknown')
                    pending_functions.add(func_name)
        except Exception as e:
            api_logger.error(f"큐 확인 중 오류: {e}")
        finally:
            # 큐에 다시 넣기
            for item in temp_queue:
                if item:  # None 체크 추가
                    await self.function_queue.put(item)
        
        # 대기 중인 함수가 없으면 완료
        is_complete = len(pending_functions) == 0
        
        if is_complete:
            api_logger.info(f"파일 '{filename}' 분석 완료 확인됨")
        else:
            api_logger.info(f"파일 '{filename}' 대기 중인 함수: {pending_functions}")
        
        return is_complete

    async def _generate_file_level_analysis(self, filename: str, user_id: str) -> str:
        """파일 전체 흐름 분석 및 종합 요약 생성"""
        
        # 1. 파일의 모든 함수 요약 수집
        pattern = f"{user_id}:func:*:{filename}:*"
        function_keys = self.redis_client.keys(pattern)
        
        function_summaries = {}
        for key in function_keys:
            # Redis key가 bytes일 수 있으므로 str로 변환
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            function_name = key_str.split(":")[-1]  # func:파일:함수명 → 함수명
            
            summary_raw = self.redis_client.get(key)
            if summary_raw:
                # bytes면 str로 변환, 이미 str이면 그대로 사용
                summary = summary_raw.decode('utf-8') if isinstance(summary_raw, bytes) else summary_raw
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
        # 4. LLM 호출하여 종합 분석
        file_analysis = await self._call_llm_for_file_analysis(analysis_prompt)
        
        # 5. 분석 결과를 Redis에 캐싱 (파일 단위)
        file_cache_key = f"{user_id}:file_analysis:{filename}"
        file_analysis_bytes = file_analysis.encode('utf-8') if isinstance(file_analysis, str) else file_analysis
        self.redis_client.setex(file_cache_key, 86400 * 3, file_analysis_bytes)  # 3일 보관
        
        return file_analysis

    async def _call_llm_for_file_analysis(self, prompt: str) -> str:
        """파일 전체 분석을 위한 LLM 호출"""
        # 임시로 LLM 호출 비활성화 - 디버깅용
        api_logger.info("파일 분석 LLM 호출 완료 (더미 응답)")
        # 더미 응답 반환 (실제 LLM 호출 대신)
        dummy_response = f"""
## 🏛️ 아키텍처 분석
파일 전체 구조 분석 완료

## 🔄 데이터 흐름 분석  
함수간 호출 관계 분석 완료

## 🚀 성능 및 확장성
성능 최적화 포인트 분석 완료

## 🛡️ 안정성 및 에러 처리
예외 처리 분석 완료

## 📈 코드 품질 평가
코드 품질 평가 완료

## 🎯 구체적 개선 제안
- 우선순위별 개선사항 분석 완료
"""
        
        return dummy_response
    
    def _find_closest_page_to_today(self, pages: list) -> dict | None:
        """
        가장 가까운 날짜에 생성된 row에 요약 저장
        """
        today = date.today()
        
        if not pages:
            return None
        
        # 오늘 날짜와의 차이를 계산하여 가장 가까운 페이지 찾기
        closest_page = None
        min_diff = float('inf')
        
        for page in pages:
            page_date = datetime.fromisoformat(page["date"]).date()
            diff = abs((today - page_date).days)
            
            if diff < min_diff:
                min_diff = diff
                closest_page = page
        
        return closest_page
    
    def _collect_function_summaries(self, user_id: str, filename: str) -> Dict[str, str]:
        """Redis에서 파일의 함수별 분석 결과 수집"""
        func_keys = self.redis_client.keys(f"{user_id}:func:*:{filename}:*")
        func_summaries = {}
        
        for key in func_keys:
            # Redis key가 bytes일 수 있으므로 str로 변환
            key_str = key.decode('utf-8') if isinstance(key, bytes) else key
            # key 형식: "{user_id}:func:{commit_sha}:{filename}:{func_name}"
            func_name = key_str.split(":")[-1]  # 마지막 부분이 함수명
            summary_raw = self.redis_client.get(key)
            if summary_raw:
                # bytes면 str로 변환, 이미 str이면 그대로 사용
                summary = summary_raw.decode('utf-8') if isinstance(summary_raw, bytes) else summary_raw
                func_summaries[func_name] = summary
        
        api_logger.info(f"파일 '{filename}': {len(func_summaries)}개 함수 분석 결과 수집")
        return func_summaries
    
    def _build_analysis_summary(self, filename: str, file_summary: str, func_summaries: Dict[str, str]) -> str:
        """토글 블록 내부에 들어갈 마크다운 콘텐츠 구성"""
        analysis_parts = [
            f"**{filename} 전체**\\n",
            file_summary,
            ""
        ]
        
        # 함수별 평가 추가
        for func_name, summary in func_summaries.items():
            analysis_parts.extend([
                f"**{func_name}()**\\n",
                summary,
                ""
            ])
        
        return "\n".join(analysis_parts)
    
    async def _find_target_page(self, user_id: str) -> Optional[Dict]:
        """현재 활성 DB에서 가장 가까운 날짜의 학습 페이지 찾기"""
        # 1. 현재 활성 DB 찾기 (Redis → Supabase 순)
        curr_db_id = await self.redis_service.get_default_db(user_id, self.redis_client)
        if not curr_db_id:
            db_result = self.supabase.table("db_webhooks")\
                .select("learning_db_id")\
                .eq("created_by", user_id)\
                .execute()
            
            if not db_result.data:
                api_logger.error(f"현재 사용중인 학습 DB를 찾을 수 없습니다.")
                return None
            curr_db_id = db_result.data[0]["learning_db_id"]
        
        # 2. 해당 DB의 페이지들 찾기 (Redis → Supabase 순) 
        pages = await self.redis_service.get_db_pages(user_id, curr_db_id, self.redis_client)
        if not pages:
            pages_result = self.supabase.table("learning_pages")\
                .select("*")\
                .eq("learning_db_id", curr_db_id)\
                .execute()
            pages = pages_result.data
        
        # 3. 가장 가까운 날짜의 페이지 선택
        closest_page = self._find_closest_page_to_today(pages)
        if not closest_page:
            api_logger.error(f"최근 학습 페이지를 찾을 수 없습니다.")
            return None
        
        return closest_page

    #[app.utils.notion_utils.py#markdown_to_notion_blocks]{}
    async def _append_analysis_to_notion(self, ai_analysis_log_page_id: str, analysis_summary: str, commit_sha: str, user_id: str):
        """분석 결과를 제목3 토글 블록으로 노션에 추가"""
        # 1. Notion 토큰 조회
        redis_service = RedisService()
        token = await redis_service.get_token(user_id, self.redis_client)

        if not token:
            # Redis에 없으면 Supabase에서 조회
            token = await get_integration_token(user_id=user_id, provider="notion", supabase=self.supabase)
            if token:
                # 조회한 토큰을 Redis에 저장 (1시간 만료)
                await redis_service.set_token(user_id, token, self.redis_client, expire_seconds=3600)

                
        if not token:
            api_logger.error(f"Notion 토큰을 찾을 수 없습니다: {user_id}")
            return
        
        # 2. NotionService로 요청 전송
        notion_service = NotionService(token=token)
        await notion_service.append_code_analysis_to_page(
            ai_analysis_log_page_id, 
            analysis_summary, 
            commit_sha
        )
        
        api_logger.info(f"Notion에 분석 결과 추가 완료: {commit_sha[:8]}")

    async def _update_notion_ai_block(self, filename: str, file_summary: str, user_id: str, commit_sha: str):
        """Notion AI 요약 블록 업데이트"""
        try:
            api_logger.info(f"파일 '{filename}' Notion 업데이트 시작")
            sys.stdout.flush()
            
            # 1. 함수별 분석 결과 수집
            func_summaries = self._collect_function_summaries(user_id, filename)
            
            # 2. 분석 요약 구성
            analysis_summary = self._build_analysis_summary(filename, file_summary, func_summaries)
            
            # 3. 타겟 페이지 찾기
            target_page = await self._find_target_page(user_id)
            if not target_page:
                api_logger.error(f"타겟 페이지를 찾을 수 없습니다.")
                return
                
            # 4. 제목3 토글 블록 생성 및 추가
            await self._append_analysis_to_notion(
                target_page["ai_block_id"], 
                analysis_summary, 
                commit_sha,
                user_id
            )
            
            api_logger.info(f"파일 '{filename}' Notion 업데이트 완료")
            sys.stdout.flush()
            
        except Exception as e:
            api_logger.error(f"Notion 업데이트 실패: {str(e)}")
            sys.stdout.flush()

    async def _generate_architecture_suggestions(self, filename: str, file_summary: str, user_id: str):
        """아키텍처 개선 제안 생성 및 별도 저장"""
        
        # 개선 제안만 추출하는 LLM 호출
        suggestions_prompt = f"""
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
        
        # Redis에 개선 제안 별도 저장 (str을 bytes로 인코딩)
        suggestions_key = f"{user_id}:suggestions:{filename}"
        suggestions_bytes = suggestions.encode('utf-8') if isinstance(suggestions, str) else suggestions
        self.redis_client.setex(suggestions_key, 86400 * 7, suggestions_bytes)  # 7일 보관
