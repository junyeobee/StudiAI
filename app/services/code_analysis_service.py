from redis.asyncio import Redis
from supabase._async.client import AsyncClient
from typing import Dict, List, Any
from app.utils.logger import api_logger
import asyncio
import re

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
        for file in files:
            if "patch" not in file:
                continue
                
            clean_code = self._strip_patch(file["patch"])
            api_logger.info(f"파일 '{file['filename']}' 분석 큐에 추가")
            tasks.append(self._enqueue_code_analysis(
                clean_code, 
                file["filename"], 
                commit_sha, 
                user_id
            ))
        
        await asyncio.gather(*tasks)
        api_logger.info("모든 코드 분석 작업이 큐에 추가됨")
    
    async def _strip_patch(self, patch: str) -> str:
        """
        diff → 수정된 코드만 남기고
        1) 메타줄 (diff/index/---/+++/@@) 제거
        2) + / - 접두어 제거
        3) 앞뒤 공백·탭 제거
        4) 완전히 빈 줄도 제거
        """
        cleaned = []
        for line in patch.splitlines():
            # ① 메타 줄 건너뛰기
            if line.startswith(("diff ", "index ", "--- ", "+++ ", "@@")):
                continue
            # ② + / - 접두어 제거
            if line[:1] in "+-":
                line = line[1:]
            # ③ 좌우 공백·탭 제거
            line = line.strip()
            # ④ 빈 줄 버리기
            if line:
                cleaned.append(line)
        return "\n".join(cleaned)
    
    async def _enqueue_code_analysis(self, code: str, filename: str, commit_sha: str, user_id: str):
        """코드 분석 작업을 큐에 넣음"""
        # 코드가 길면 적절히 분할
        chunks = self._split_code_if_needed(code)
        
        for i, chunk in enumerate(chunks):
            metadata = self._extract_metadata(chunk)
            await self.queue.put({
                "code": chunk,
                "metadata": metadata,
                "filename": filename,
                "commit_sha": commit_sha,
                "user_id": user_id,
                "chunk_index": i,
                "total_chunks": len(chunks)
            })
            api_logger.info(f"'{filename}' 청크 {i+1}/{len(chunks)} 큐에 추가됨")
    
    def _split_code_if_needed(self, code: str) -> List[str]:
        """코드가 너무 길면 여러 청크로 분할"""
        # 임시로 단순 구현 - 실제로는 토큰 수나 함수/클래스 단위로 분할 필요
        max_length = 3000  # 예시 길이 제한
        
        if len(code) <= max_length:
            return [code]
            
        # 단순하게 청크 단위로 분할 (실제로는 더 정교한 로직 필요)
        chunks = []
        for i in range(0, len(code), max_length):
            chunks.append(code[i:i+max_length])
        
        return chunks
    
    def _extract_metadata(self, code: str) -> Dict[str, Any]:
        """코드 청크에서 메타데이터 추출"""
        metadata = {}
        
        # 주석에서 메타데이터 추출 로직
        lines = code.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('#'):
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
                # 첫 번째 주석만 처리하고 중단
                break
        
        return metadata
    
    async def process_queue(self):
        """비동기로 큐 처리"""
        api_logger.info("코드 분석 큐 처리 시작")
        while True:
            item = await self.queue.get()
            try:
                api_logger.info(f"코드 분석 처리: {item['filename']} 청크 {item['chunk_index']+1}/{item['total_chunks']}")
                # LLM API 호출 및 결과 저장
                result = await self._call_llm_api(item)
                await self._store_analysis_result(item, result)
            except Exception as e:
                api_logger.error(f"코드 분석 처리 실패: {str(e)}")
            finally:
                self.queue.task_done()
    

    # 여기 안됨.
    async def _call_llm_api(self, item: Dict) -> str:
        """LLM API 호출 (실제 구현 필요)"""
        # 임시 구현 - 실제 LLM API 호출로 대체 필요
        api_logger.info(f"LLM API 호출: {item['filename']} 청크 {item['chunk_index']+1}")
        # TODO: 실제 LLM API 호출 구현
        return f"코드 분석 결과: {item['filename']}"
    
    async def _store_analysis_result(self, item: Dict, result: str):
        """분석 결과 저장"""
        api_logger.info(f"분석 결과 저장: {item['filename']} 청크 {item['chunk_index']+1}")
        
        key = f"{item['user_id']}:{item['filename']}:{item['commit_sha']}:{item['chunk_index']}"
        
        # Redis에 결과 저장 (임시)
        await self.redis_client.set(key, result, ex=86400)  # 24시간 유지
        
        # TODO: Supabase에 결과 저장 (실제 구현 필요)