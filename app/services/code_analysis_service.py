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
import uuid
import traceback
from app.core.config import settings
# 버퍼링 비활성화
os.environ["PYTHONUNBUFFERED"] = "1"
import concurrent.futures

class CodeAnalysisService:
    """함수 중심 코드 분석 및 LLM 처리 서비스 - 24/7 운영 최적화 버전"""
    
    # ✅ Step 5: 공유 ThreadPoolExecutor 클래스 변수
    _shared_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
    _executor_lock = asyncio.Lock()
    
    def __init__(self, redis_client: Redis, supabase: AsyncClient):
        self.redis_client = redis_client
        self.redis_service = RedisService()
        self.supabase = supabase
        self.function_queue = asyncio.Queue()
        self.api_key = settings.OPENAI_API_KEY
    
    # ✅ Step 5: 공유 ThreadPoolExecutor 관리 메서드들
    @classmethod
    async def _get_shared_executor(cls) -> concurrent.futures.ThreadPoolExecutor:
        """공유 ThreadPoolExecutor 반환 (지연 초기화, 이중 체크 잠금)"""
        if cls._shared_executor is None:
            async with cls._executor_lock:
                if cls._shared_executor is None:
                    cls._shared_executor = concurrent.futures.ThreadPoolExecutor(
                        max_workers=4,
                        thread_name_prefix="llm_worker"
                    )
                    api_logger.info("공유 ThreadPoolExecutor 생성 완료 (max_workers=4)")
        return cls._shared_executor
    
    @classmethod
    async def cleanup_executor(cls):
        """서비스 종료시 ThreadPool 정리"""
        if cls._shared_executor:
            cls._shared_executor.shutdown(wait=True)
            cls._shared_executor = None
            api_logger.info("공유 ThreadPoolExecutor 종료 완료")
    
    # ✅ Step 3: Hash 기반 함수 요약 저장 메서드
    async def _save_function_summary_to_hash(self, user_id: str, commit_sha: str, 
                                           filename: str, func_name: str, summary: str):
        """함수 요약을 Hash 형태로 저장 (원자적 업데이트)"""
        file_key = f"{user_id}:func:{commit_sha}:{filename}"
        
        def _sync_hash_save():
            try:
                self.redis_client.hset(file_key, func_name, summary)
                self.redis_client.expire(file_key, 86400 * 7)  # 7일 보관
                return True
            except Exception as e:
                api_logger.error(f"Redis Hash 저장 실패 ({func_name}): {e}")
                api_logger.error(traceback.format_exc())
                raise
        
        try:
            executor = await self._get_shared_executor()
            await asyncio.get_event_loop().run_in_executor(executor, _sync_hash_save)
            api_logger.info(f"함수 요약 Hash 저장 완료: {func_name} → {file_key}")
            
        except Exception as e:
            api_logger.error(f"함수 요약 저장 실패 ({func_name}): {e}")
            api_logger.error(traceback.format_exc())
            raise
    
    # ✅ Step 3: Hash에서 함수별 분석 결과 수집 (keys() 제거)
    async def _collect_function_summaries(self, user_id: str, filename: str, commit_sha: str) -> Dict[str, str]:
        """Hash에서 함수별 분석 결과 수집 (O(1) 조회)"""
        file_key = f"{user_id}:func:{commit_sha}:{filename}"
        
        def _sync_hash_collect():
            try:
                summaries_hash = self.redis_client.hgetall(file_key)
                func_summaries = {}
                for func_name_bytes, summary_bytes in summaries_hash.items():
                    func_name = func_name_bytes.decode('utf-8') if isinstance(func_name_bytes, bytes) else func_name_bytes
                    summary = summary_bytes.decode('utf-8') if isinstance(summary_bytes, bytes) else summary_bytes
                    func_summaries[func_name] = summary
                return func_summaries
            except Exception as e:
                api_logger.error(f"Redis Hash 수집 실패 ({filename}): {e}")
                api_logger.error(traceback.format_exc())
                return {}
        
        try:
            executor = await self._get_shared_executor()
            func_summaries = await asyncio.get_event_loop().run_in_executor(executor, _sync_hash_collect)
            
            api_logger.info(f"파일 '{filename}': {len(func_summaries)}개 함수 분석 결과 수집 (커밋: {commit_sha[:8]})")
            return func_summaries
            
        except Exception as e:
            api_logger.error(f"함수 요약 수집 실패 ({filename}): {e}")
            api_logger.error(traceback.format_exc())
            return {}
    
    # ✅ Step 2,4: Redis 카운터 기반 pending 관리 (I/O 오프로드)
    async def _increment_pending_count(self, user_id: str, commit_sha: str, filename: str):
        """파일의 대기 중인 함수 수 증가 (commit_sha 포함, I/O 오프로드)"""
        counter_key = f"{user_id}:pending:{commit_sha}:{filename}"
        
        def _sync_incr():
            try:
                pipe = self.redis_client.pipeline()
                pipe.incr(counter_key)
                pipe.expire(counter_key, 3600 * 3)  # 3시간 TTL
                pipe.execute()
            except Exception as e:
                api_logger.error(f"Redis pending 증가 실패: {e}")
                api_logger.error(traceback.format_exc())
                raise
        
        try:
            executor = await self._get_shared_executor()
            await asyncio.get_event_loop().run_in_executor(executor, _sync_incr)
            api_logger.debug(f"pending 카운터 증가: {counter_key}")
        except Exception as e:
            api_logger.error(f"pending 카운터 증가 실패: {e}")
            api_logger.error(traceback.format_exc())
            raise
    
    async def _decrement_pending_count(self, user_id: str, commit_sha: str, filename: str) -> int:
        """파일의 대기 중인 함수 수 감소 후 남은 수 반환 (I/O 오프로드)"""
        counter_key = f"{user_id}:pending:{commit_sha}:{filename}"
        
        def _sync_decr():
            try:
                remaining = self.redis_client.decr(counter_key)
                if remaining <= 0:
                    self.redis_client.delete(counter_key)
                    return 0
                return remaining
            except Exception as e:
                api_logger.error(f"Redis pending 감소 실패: {e}")
                api_logger.error(traceback.format_exc())
                return 0
        
        try:
            executor = await self._get_shared_executor()
            remaining = await asyncio.get_event_loop().run_in_executor(executor, _sync_decr)
            api_logger.debug(f"pending 카운터 감소: {counter_key} → {remaining}")
            return remaining
            
        except Exception as e:
            api_logger.error(f"pending 카운터 감소 실패: {e}")
            api_logger.error(traceback.format_exc())
            return 0

    async def analyze_code_changes(self, files: List[Dict], owner: str, repo: str, commit_sha: str, user_id: str):
        """코드 변경 분석 처리 → 자동 큐 처리 포함"""
        api_logger.info(f"함수별 분석 시작: {len(files)}개 파일")
        
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
        
        # ✅ Step 4: enqueue 완료 후 자동으로 큐 처리 트리거
        await self.process_queue()
    
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
        """함수별 분석 작업을 큐에 추가 - 변경된 함수 + 새 파일 (Hash 캐시 확인)"""
        
        # 변경사항도 없고 새 파일도 아니면 스킵
        if not func_info.get('has_changes', True) and not func_info.get('is_new_file', False): 
            api_logger.info(f"함수 '{func_info['name']}' 변경 없음")
            return
        
        # ✅ Step 3: Hash 기반 캐시 확인 (개별 키 제거)
        file_key = f"{user_id}:func:{commit_sha}:{func_info['filename']}"
        
        def _sync_cache_check():
            try:
                return self.redis_client.hget(file_key, func_info['name'])
            except Exception as e:
                api_logger.error(f"Redis Hash 캐시 확인 실패: {e}")
                return None
        
        try:
            executor = await self._get_shared_executor()
            cached_result = await asyncio.get_event_loop().run_in_executor(executor, _sync_cache_check)
        except Exception as e:
            api_logger.error(f"캐시 확인 중 오류: {e}")
            cached_result = None
        
        # 캐시가 있고 변경사항이 없는 기존 파일만 캐시 사용 (새 파일은 항상 분석)
        if cached_result and not func_info.get('has_changes', True) and not func_info.get('is_new_file', False):
            api_logger.info(f"함수 '{func_info['name']}' 변경 없음, 캐시 사용")
            return
        
        # 변경된 함수이거나 새 파일인 경우 큐에 추가
        if func_info.get('has_changes', True) or func_info.get('is_new_file', False):
            # ✅ Step 4: pending 카운터 증가
            await self._increment_pending_count(user_id, commit_sha, func_info['filename'])
            
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
    
    # ✅ Step 4: 큐 처리 루프 개선 (wait_for timeout 방식)
    async def process_queue(self):
        """함수별 분석 큐 처리 - 새로 추가된 아이템도 놓치지 않음"""
        api_logger.info("함수별 분석 큐 처리 시작")
        
        processed_count = 0
        while True:
            try:
                # 큐가 비어있으면 0.1초 후 TimeoutError 발생 → 루프 탈출
                item = await asyncio.wait_for(self.function_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                break
            
            try:
                await self._analyze_function(item)
                processed_count += 1
                api_logger.info(f"진행상황: {processed_count}개 함수 처리 완료")
            except Exception as e:
                api_logger.error(f"함수 분석 처리 오류: {e}")
                api_logger.error(traceback.format_exc())
                
                # ✅ 실패시에도 pending 카운터 감소
                try:
                    user_id = item.get('user_id')
                    commit_sha = item.get('commit_sha') 
                    filename = item.get('function_info', {}).get('filename')
                    if user_id and commit_sha and filename:
                        await self._decrement_pending_count(user_id, commit_sha, filename)
                except Exception as decr_error:
                    api_logger.error(f"실패 후 카운터 감소 오류: {decr_error}")
                    api_logger.error(traceback.format_exc())
            finally:
                self.function_queue.task_done()
        
        api_logger.info(f"모든 함수 분석 완료 (총 {processed_count}개 처리)")
    
    async def _analyze_function(self, item: Dict):
        """개별 함수 분석 처리 (Step 3,4: Hash 저장 + pending 카운터)"""
        func_info = item['function_info']
        func_name = func_info['name']
        filename = func_info['filename']
        commit_sha = item['commit_sha']
        user_id = item['user_id']
        
        api_logger.info(f"함수 '{func_name}' 분석 시작")
        
        try:
            # ✅ Step 3: Hash에서 이전 분석 결과 조회 (개별 키 제거)
            file_key = f"{user_id}:func:{commit_sha}:{filename}"
            
            def _sync_prev_check():
                try:
                    return self.redis_client.hget(file_key, func_name)
                except Exception as e:
                    api_logger.error(f"이전 요약 조회 실패: {e}")
                    return None
            
            executor = await self._get_shared_executor()
            previous_summary_bytes = await asyncio.get_event_loop().run_in_executor(executor, _sync_prev_check)
            previous_summary = previous_summary_bytes.decode('utf-8') if previous_summary_bytes else None
        
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
            
            # ✅ Step 3: Hash 방식으로 요약 저장
            await self._save_function_summary_to_hash(
                user_id, commit_sha, filename, func_name, summary
            )
            
            # ✅ Step 4: pending 카운터 감소 및 완료 확인
            remaining = await self._decrement_pending_count(user_id, commit_sha, filename)
            api_logger.info(f"함수 '{func_name}' 분석 완료 (남은 함수: {remaining}개)")
            
            # 파일 분석 완료시 Notion 업데이트
            if remaining == 0:
                await self._handle_file_analysis_complete(func_info, user_id, commit_sha, item['repo'])
                
        except Exception as e:
            # ✅ Step 4: 실패시에도 pending 카운터 감소
            await self._decrement_pending_count(user_id, commit_sha, filename)
            api_logger.error(f"함수 분석 실패 ({func_name}): {e}")
            api_logger.error(traceback.format_exc())
            raise

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
    
    # ✅ Step 6: LLM 이중 타임아웃 적용
    async def _call_llm_for_function(self, func_info: Dict, code: str, metadata: Dict, 
                                   previous_summary: str = None, reference_content: str = None,
                                   chunk_index: int = 0, total_chunks: int = 1) -> str:
        """함수별 LLM 분석 호출 (Step 6: 이중 타임아웃 30s+35s)"""
        
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
        
        # ✅ Step 6: 이중 타임아웃 동기 함수 분리
        def _sync_llm_call():
            """동기식 LLM 호출 (내부 타임아웃 30초)"""
            try:
                # OpenAI 클라이언트 설정 (GPT-4o mini API)
                client = OpenAI(
                    api_key=self.api_key
                )
                
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "당신은 코드 분석 전문가입니다. 주어진 함수를 분석하여 명확하고 유용한 정보를 제공하세요."},
                        {"role": "user", "content": full_prompt}
                    ],
                    timeout=60  # ✅ Step 6: LLM 내부 타임아웃 (함수: 60초, GPT-4o mini 최적화)
                )
                
                return response.choices[0].message.content
                
            except Exception as e:
                api_logger.error(f"LLM 호출 실패(동기 단계): {e}")
                api_logger.error(traceback.format_exc())
                return f"**기능 요약**: {func_info['name']} 함수\n**분석 상태**: LLM 분석 실패 - {e}"
        
        try:
            api_logger.info(f"함수 '{func_info['name']}' LLM 분석 시작")
            
            # ✅ Step 5: 공유 ThreadPoolExecutor 사용
            executor = await self._get_shared_executor()
            
            # ✅ Step 6: 이중 타임아웃 (LLM 60초 + asyncio 90초, GPT-4o mini 최적화)
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, _sync_llm_call),
                timeout=90  # ✅ Step 6: 외부 타임아웃 (90초, GPT-4o mini 최적화)
            )
            
            api_logger.info(f"함수 '{func_info['name']}' LLM 분석 완료")
            return result
            
        except asyncio.TimeoutError:
            api_logger.error(f"함수 '{func_info['name']}' LLM 호출 타임아웃 (90초)")
            return f"**기능 요약**: {func_info['name']} 함수\n**분석 상태**: 타임아웃으로 인한 분석 실패"
        except Exception as e:
            api_logger.error(f"비동기 LLM 호출 실패: {e}")
            api_logger.error(traceback.format_exc())
            return f"**기능 요약**: {func_info['name']} 함수\n**분석 상태**: LLM 분석 실패 - {e}"
    
    # ✅ Step 8: UUID 기반 Request ID 충돌 방지
    async def _fetch_reference_function(self, reference_file: str, owner: str, repo: str, commit_sha: str, user_id: str) -> str:
        """참조 파일의 함수 요약을 Redis Hash에서 조회 (Step 3: keys() 제거)"""
        # 파일에서 특정 함수가 지정되었는지 확인
        if '#' in reference_file:
            file_path, func_name = reference_file.split('#', 1)
            file_key = f"{user_id}:func:{commit_sha}:{file_path}"
            
            # ✅ Step 3: Hash에서 특정 함수 조회 (개별 키 제거)
            def _sync_ref_get():
                try:
                    return self.redis_client.hget(file_key, func_name)
                except Exception as e:
                    api_logger.error(f"참조 함수 조회 실패: {e}")
                    return None
            
            try:
                executor = await self._get_shared_executor()
                cached_content_bytes = await asyncio.get_event_loop().run_in_executor(executor, _sync_ref_get)
                if cached_content_bytes:
                    return cached_content_bytes.decode('utf-8') if isinstance(cached_content_bytes, bytes) else cached_content_bytes
            except Exception as e:
                api_logger.error(f"참조 함수 조회 중 오류: {e}")
        else:
            # 파일 전체 참조인 경우 주요 함수들 조회
            file_key = f"{user_id}:func:{commit_sha}:{reference_file}"
            
            # ✅ Step 3: Hash 전체 조회 (keys() 제거)
            try:
                func_summaries = await self._collect_function_summaries(user_id, reference_file, commit_sha)
                
                if func_summaries:
                    all_summaries = []
                    for func_name, summary in func_summaries.items():
                        all_summaries.append(f"**{func_name}():**\n{summary}")
                    
                    if all_summaries:
                        return "\n\n".join(all_summaries)
            except Exception as e:
                api_logger.error(f"참조 파일 전체 조회 실패: {e}")
        
        # Redis에 없으면 파일 내용 요청 (기존 방식 활용)
        return await self._request_reference_file_content(reference_file, owner, repo, commit_sha)
    
    async def _request_reference_file_content(self, reference_file: str, owner: str, repo: str, commit_sha: str) -> str:
        """GitHub에서 참조 파일 내용 요청 (Step 8: UUID 기반 Request ID)"""
        # ✅ Step 8: UUID로 완전 유니크한 Request ID 생성
        request_id = str(uuid.uuid4())
        
        request_data = {
            'path': reference_file,
            'commit_sha': commit_sha,
            'request_id': request_id
        }
        
        request_key = f"ref_request:{owner}:{repo}:{request_id}"
        response_key = f"ref_response:{owner}:{repo}:{request_id}"
        
        def _sync_request_save():
            try:
                # JSON 데이터를 bytes로 인코딩해서 저장
                request_data_json = json.dumps(request_data)
                request_data_bytes = request_data_json.encode('utf-8')
                self.redis_client.setex(request_key, 300, request_data_bytes)
            except Exception as e:
                api_logger.error(f"참조 파일 요청 저장 실패: {e}")
                api_logger.error(traceback.format_exc())
                raise
        
        try:
            executor = await self._get_shared_executor()
            await asyncio.get_event_loop().run_in_executor(executor, _sync_request_save)
        except Exception as e:
            api_logger.error(f"참조 파일 요청 중 오류: {e}")
            return ""
        
        # 5초 폴링 대기
        for _ in range(10):
            def _sync_response_check():
                try:
                    return self.redis_client.get(response_key)
                except Exception as e:
                    api_logger.error(f"참조 파일 응답 확인 실패: {e}")
                    return None
            
            try:
                executor = await self._get_shared_executor()
                response_str = await asyncio.get_event_loop().run_in_executor(executor, _sync_response_check)
                if response_str:
                    response_data = json.loads(response_str)
                    if response_data.get('status') == 'success':
                        return response_data.get('content', '')
            except Exception as e:
                api_logger.error(f"참조 파일 응답 처리 중 오류: {e}")
            
            await asyncio.sleep(0.5)
        
        return ""
    
    # ✅ Step 4: 파일 완료 처리 로직 분리
    async def _handle_file_analysis_complete(self, func_info: Dict, user_id: str, commit_sha: str, repo: str):
        """파일의 모든 함수 분석 완료시 처리"""
        filename = func_info['filename']
        api_logger.info(f"파일 '{filename}' 모든 함수 분석 완료 - Notion 업데이트 시작")
        
        try:
            # 파일별 종합 분석 수행
            file_summary = await self._generate_file_level_analysis(filename, user_id, commit_sha)
            
            # Notion AI 요약 블록 업데이트
            await self._update_notion_ai_block(filename, file_summary, user_id, commit_sha, repo)
            
            # 아키텍처 개선 제안 생성
            await self._generate_architecture_suggestions(filename, file_summary, user_id)
            
            api_logger.info(f"파일 '{filename}' Notion 업데이트 완료")
            
        except Exception as e:
            api_logger.error(f"파일 완료 처리 실패 ({filename}): {e}")
            api_logger.error(traceback.format_exc())

    async def _generate_file_level_analysis(self, filename: str, user_id: str, commit_sha: str) -> str:
        """파일 전체 흐름 분석 및 종합 요약 생성 (Step 1: Hash 기반)"""
        
        # ✅ Step 1: Hash에서 함수별 요약 수집 (keys() 제거)
        file_key = f"{user_id}:func:{commit_sha}:{filename}"
        summaries_hash = self.redis_client.hgetall(file_key)
        
        function_summaries = {}
        for func_name_bytes, summary_bytes in summaries_hash.items():
            func_name = func_name_bytes.decode('utf-8') if isinstance(func_name_bytes, bytes) else func_name_bytes
            summary = summary_bytes.decode('utf-8') if isinstance(summary_bytes, bytes) else summary_bytes
            function_summaries[func_name] = summary
        
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
        
        # 4. 프롬프트 정리 (탭문자, 연속 공백 제거)
        analysis_prompt = re.sub(r'\t+', ' ', analysis_prompt)  # 탭을 공백으로
        analysis_prompt = re.sub(r' +', ' ', analysis_prompt)   # 연속 공백을 하나로
        analysis_prompt = re.sub(r'\n\s*\n', '\n\n', analysis_prompt)  # 연속 빈줄을 두줄로
        
        # 5. 4800자로 청크 분할
        if len(analysis_prompt) <= 4800:
            # 단일 청크 처리
            file_analysis = await self._call_llm_for_file_analysis(analysis_prompt)
        else:
            # 다중 청크 연속 처리
            chunks = self._split_prompt_into_chunks(analysis_prompt, 4800)
            file_analysis = await self._process_multi_chunk_analysis(filename, chunks)
        
        # 6. 분석 결과를 Redis에 캐싱 (파일 단위)
        file_cache_key = f"{user_id}:file_analysis:{filename}"
        file_analysis_bytes = file_analysis.encode('utf-8') if isinstance(file_analysis, str) else file_analysis
        self.redis_client.setex(file_cache_key, 86400 * 3, file_analysis_bytes)  # 3일 보관
        
        return file_analysis

    def _split_prompt_into_chunks(self, prompt: str, max_length: int = 4800) -> List[str]:
        """프롬프트를 지정된 길이로 청크 분할"""
        if len(prompt) <= max_length:
            return [prompt]
        
        chunks = []
        lines = prompt.split('\n')
        current_chunk = ""
        
        for line in lines:
            # 현재 줄을 추가했을 때 길이 확인
            test_chunk = current_chunk + '\n' + line if current_chunk else line
            
            if len(test_chunk) <= max_length:
                current_chunk = test_chunk
            else:
                # 현재 청크가 비어있지 않으면 저장
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = line
                else:
                    # 단일 라인이 너무 긴 경우 강제 분할
                    while len(line) > max_length:
                        chunks.append(line[:max_length])
                        line = line[max_length:]
                    current_chunk = line
        
        # 마지막 청크 추가
        if current_chunk:
            chunks.append(current_chunk)
        
        api_logger.info(f"프롬프트를 {len(chunks)}개 청크로 분할 (각 청크 최대 {max_length}자)")
        return chunks

    async def _process_multi_chunk_analysis(self, filename: str, chunks: List[str]) -> str:
        """다중 청크 파일 분석의 연속적 요약 처리"""
        current_summary = None
        
        for i, chunk in enumerate(chunks):
            api_logger.info(f"파일 '{filename}' 청크 {i+1}/{len(chunks)} 분석 시작")
            
            # 첫 번째 청크가 아니면 이전 요약을 포함한 프롬프트 구성
            if current_summary:
                enhanced_prompt = f"""
이전 분석 결과:
{current_summary}

위 분석을 바탕으로 다음 추가 정보를 분석하고 통합된 요약을 제공하세요:

{chunk}

**중요**: 이전 분석과 현재 정보를 종합하여 완전한 파일 분석을 제공하세요.
"""
            else:
                enhanced_prompt = chunk
            
            # LLM 호출
            chunk_summary = await self._call_llm_for_file_analysis(enhanced_prompt)
            current_summary = chunk_summary  # 다음 청크에서 사용할 요약 업데이트
            
            api_logger.info(f"파일 '{filename}' 청크 {i+1}/{len(chunks)} 분석 완료")
        
        api_logger.info(f"파일 '{filename}' 전체 다중 청크 분석 완료")
        return current_summary

    async def _call_llm_for_file_analysis(self, prompt: str) -> str:
        """파일 전체 분석을 위한 LLM 호출 (Step 6: 이중 타임아웃 60s+65s)"""
        
        # ✅ Step 6: 이중 타임아웃 동기 함수 분리
        def _sync_file_analysis_call():
            """동기식 파일 분석 LLM 호출 (내부 타임아웃 60초)"""
            try:
                # OpenAI 클라이언트 설정 (GPT-4o mini API)
                client = OpenAI(
                    api_key=self.api_key
                )
                
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "당신은 소프트웨어 아키텍처 전문가입니다. 파일 전체의 구조와 흐름을 분석하여 개선 방안을 제시하세요."},
                        {"role": "user", "content": prompt}
                    ],
                    timeout=120  # ✅ Step 6: LLM 내부 타임아웃 (파일: 120초, GPT-4o mini 최적화)
                )
                
                return response.choices[0].message.content
                
            except Exception as e:
                api_logger.error(f"LLM 호출 실패(동기 단계): {e}")
                api_logger.error(traceback.format_exc())
                return f"""
## 🏛️ 아키텍처 분석
타임아웃으로 인한 분석 실패

## 📝 분석 상태
LLM 호출 타임아웃 (120초)
"""
        
        try:
            api_logger.info("파일 전체 분석 LLM 호출 시작")
            
            # ✅ Step 5: 공유 ThreadPoolExecutor 사용
            executor = await self._get_shared_executor()
            
            # ✅ Step 6: 이중 타임아웃 (LLM 120초 + asyncio 150초, GPT-4o mini 최적화)
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(executor, _sync_file_analysis_call),
                timeout=150  # ✅ Step 6: 외부 타임아웃 (150초, GPT-4o mini 최적화)
            )
            
            api_logger.info("파일 전체 분석 LLM 호출 완료")
            return result
            
        except asyncio.TimeoutError:
            api_logger.error("파일 분석 LLM 호출 타임아웃 (150초)")
            return f"""
## 🏛️ 아키텍처 분석
타임아웃으로 인한 분석 실패

## 📝 분석 상태
LLM 호출 타임아웃 (150초)
"""
        except Exception as e:
            api_logger.error(f"비동기 파일 분석 LLM 호출 실패: {e}")
            api_logger.error(traceback.format_exc())
            return f"""
## 🏛️ 아키텍처 분석
LLM 호출 실패

## 📝 분석 상태
LLM 호출 오류: {e}

## 🔧 해결 방안
로컬 LLM 서버 상태를 확인하세요.
"""

    async def _update_notion_ai_block(self, filename: str, file_summary: str, user_id: str, commit_sha: str, repo: str):
        """Notion AI 요약 블록 업데이트"""
        try:
            api_logger.info(f"파일 '{filename}' Notion 업데이트 시작")
            sys.stdout.flush()
            
            # 1. 함수별 분석 결과 수집
            func_summaries = await self._collect_function_summaries(user_id, filename, commit_sha)
            
            # 2. 분석 요약 구성
            analysis_summary = self._build_analysis_summary(filename, file_summary, func_summaries)
            
            # 3. 타겟 페이지 찾기
            target_page = await self._find_target_page(user_id, repo)
            if not target_page:
                api_logger.error(f"타겟 페이지를 찾을 수 없습니다.")
                return
            api_logger.info(f"타겟 페이지: {target_page}")
            # 4. 제목3 토글 블록 생성 및 추가
            await self._append_analysis_to_notion(
                target_page["ai_block_id"], 
                analysis_summary, 
                commit_sha,
                user_id,
                repo
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
    
    def _build_analysis_summary(self, filename: str, file_summary: str, func_summaries: Dict[str, str]) -> str:
        """토글 블록 내부에 들어갈 마크다운 콘텐츠 구성"""
        analysis_parts = [
            f"## {filename} 전체\n",
            file_summary,
            ""
        ]
        
        # 함수별 평가 추가
        for func_name, summary in func_summaries.items():
            analysis_parts.extend([
                f"### {func_name}()\n",
                summary,
                ""
            ])

        result = "\n".join(analysis_parts)
        api_logger.info(f"분석 요약 구성 완료: {len(analysis_parts)}개 파트")
        return result
    
    async def _find_target_page(self, user_id: str, repo: str) -> Optional[Dict]:
        """현재 활성 DB에서 가장 가까운 날짜의 학습 페이지 찾기"""
        try:
            api_logger.info(f"_find_target_page 시작: {user_id}, repo: {repo}")
            
            # 1. 현재 활성 DB 찾기 (Redis → Supabase 순) - repo별로 구분
            def _sync_redis_db_get():
                try:
                    return self.redis_client.get(f"user:{user_id}:{repo}:db_id")
                except Exception as e:
                    api_logger.error(f"Redis DB ID 조회 실패: {e}")
                    return None
            
            executor = await self._get_shared_executor()
            curr_db_id = await asyncio.get_event_loop().run_in_executor(executor, _sync_redis_db_get)
            if curr_db_id:
                curr_db_id = curr_db_id.decode('utf-8') if isinstance(curr_db_id, bytes) else curr_db_id
            api_logger.info(f"Redis에서 DB ID 조회 완료: {curr_db_id}")
            
            if not curr_db_id:
                api_logger.info("Redis에 DB ID 없음, Supabase에서 조회")
                try:
                    # repo_name으로 해당 레포의 learning_db_id 찾기
                    db_result = await self.supabase.table("db_webhooks")\
                        .select("learning_db_id")\
                        .eq("created_by", user_id)\
                        .eq("repo_name", repo)\
                        .execute()
                    api_logger.info("Supabase DB 조회 완료")
                    
                    if not db_result.data:
                        api_logger.warning(f"사용자 {user_id}의 레포 {repo}에 대한 활성 학습 DB가 존재하지 않습니다")
                        return None
                    curr_db_id = db_result.data[0]["learning_db_id"]
                except Exception as e:
                    api_logger.error(f"Supabase DB 조회 오류: {e}")
                    api_logger.error(traceback.format_exc())
                    return None
            
            api_logger.info(f"최종 DB ID: {curr_db_id}")
            
            # 2. 해당 DB의 페이지들 찾기 (Redis → Supabase 순)
            pages_key = f"user:{user_id}:db:{curr_db_id}:pages"
            
            def _sync_redis_pages_get():
                try:
                    return self.redis_client.get(pages_key)
                except Exception as e:
                    api_logger.error(f"Redis 페이지 조회 실패: {e}")
                    return None
            
            pages_data = await asyncio.get_event_loop().run_in_executor(executor, _sync_redis_pages_get)
            pages = None
            if pages_data:
                try:
                    pages_str = pages_data.decode('utf-8') if isinstance(pages_data, bytes) else pages_data
                    pages = json.loads(pages_str)
                except Exception as e:
                    api_logger.error(f"Redis 페이지 데이터 파싱 실패: {e}")
                    
            api_logger.info(f"Redis에서 페이지 조회 완료: {len(pages) if pages else 0}개")
            
            if not pages:
                api_logger.info("Redis에 페이지 없음, Supabase에서 조회")
                pages_result = await self.supabase.table("learning_pages")\
                    .select("*")\
                    .eq("learning_db_id", curr_db_id)\
                    .execute()
                api_logger.info("Supabase 페이지 조회 완료")
                pages = pages_result.data
                api_logger.info(f"Supabase에서 페이지 조회 완료: {pages}")
            # 3. 가장 가까운 날짜의 페이지 선택
            closest_page = self._find_closest_page_to_today(pages)
            if not closest_page:
                api_logger.warning(f"사용자 {user_id}의 레포 {repo}에 대한 학습 페이지가 존재하지 않습니다")
                return None
            
            api_logger.info("_find_target_page 완료")
            return closest_page
        except Exception as e:
            api_logger.error(f"_find_target_page 오류: {e}")
            api_logger.error(traceback.format_exc())
            return None

    #[app.utils.notion_utils.py#markdown_to_notion_blocks]{}
    async def _append_analysis_to_notion(self, ai_analysis_log_page_id: str, analysis_summary: str, commit_sha: str, user_id: str, repo: str):
        """분석 결과를 제목3 토글 블록으로 노션에 추가 (I/O 오프로드)"""
        # 1. Notion 토큰 조회 (I/O 오프로드)
        token_key = f"user:{user_id}:notion_token"
        api_logger.info(f"Redis에서 토큰 조회 시도: {token_key}")
        
        def _sync_token_get():
            try:
                return self.redis_client.get(token_key)
            except Exception as e:
                api_logger.error(f"Redis 토큰 조회 실패: {e}")
                return None
        
        try:
            executor = await self._get_shared_executor()
            token = await asyncio.get_event_loop().run_in_executor(executor, _sync_token_get)
            
            # Redis에 있으면 bytes를 str로 변환
            if token:
                token = token.decode('utf-8') if isinstance(token, bytes) else token
                api_logger.info(f"Redis에서 토큰 조회 성공: {token[:20]}...")
            else:
                api_logger.info("Redis에 토큰이 없음, Supabase에서 조회")
        except Exception as e:
            api_logger.error(f"Redis 토큰 조회 중 오류: {e}")
            token = None

        if not token:
            # Redis에 없으면 Supabase에서 조회
            try:
                api_logger.info("Supabase 토큰 조회 시작")
                # ✅ Step 1: Supabase 호출에 await 추가
                integration_result = await self.supabase.table("user_integrations")\
                    .select("*")\
                    .eq("user_id", user_id)\
                    .eq("provider", "notion")\
                    .execute()
                
                api_logger.info(f"Supabase 조회 결과: {len(integration_result.data)}개")
                
                if integration_result.data:
                    # ✅ Step 10: AES 복호화를 run_in_executor로 오프로드
                    def _sync_decrypt():
                        try:
                            import base64
                            from Crypto.Cipher import AES
                            from app.core.config import settings
                            
                            res = integration_result.data[0]
                            encryption_key = base64.b64decode(settings.ENCRYPTION_KEY)
                            iv = base64.b64decode(res["token_iv"])
                            
                            token_data = base64.b64decode(res["access_token"])
                            encrypted_token = token_data[:-16]
                            tag = token_data[-16:]
                            
                            cipher = AES.new(encryption_key, AES.MODE_GCM, nonce=iv)
                            return cipher.decrypt_and_verify(encrypted_token, tag).decode('utf-8')
                        except Exception as e:
                            api_logger.error(f"토큰 복호화 실패: {e}")
                            api_logger.error(traceback.format_exc())
                            return None
                    
                    api_logger.info("토큰 복호화 시작")
                    token = await asyncio.get_event_loop().run_in_executor(executor, _sync_decrypt)
                    
                    if token:
                        api_logger.info(f"토큰 복호화 성공: {token[:20]}...")
                        
                        # ✅ Step 10: Redis setex를 run_in_executor로 오프로드
                        def _sync_token_save():
                            try:
                                self.redis_client.setex(token_key, 3600, token)
                            except Exception as e:
                                api_logger.error(f"Redis 토큰 저장 실패: {e}")
                        
                        await asyncio.get_event_loop().run_in_executor(executor, _sync_token_save)
                        api_logger.info("Redis에 토큰 저장 완료")
                    
            except Exception as e:
                api_logger.error(f"토큰 조회/복호화 실패: {e}")
                api_logger.error(traceback.format_exc())
                token = None
                
        if not token:
            api_logger.error(f"Notion 토큰을 찾을 수 없습니다: {user_id}")
            return
        
        api_logger.info(f"최종 토큰 확인: {token[:20]}...")
        
        # 2. NotionService로 요청 전송
        try:
            notion_service = NotionService(token=token)
            await notion_service.append_code_analysis_to_page(
                ai_analysis_log_page_id, 
                analysis_summary, 
                commit_sha
            )
            api_logger.info(f"Notion에 분석 결과 추가 완료: {commit_sha[:8]}")
        except Exception as e:
            api_logger.error(f"Notion 서비스 호출 실패: {e}")
            api_logger.error(traceback.format_exc())