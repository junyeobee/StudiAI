from redis import Redis
from supabase._async.client import AsyncClient
from typing import Dict, List, Any
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
                api_logger.info(f"파일 '{file['filename']}' 전체 내용 분석 (길이: {len(code_to_analyze)})")
            else:
                # 패치에서 실제 코드만 추출
                code_to_analyze = self._strip_patch(file["patch"])
                api_logger.info(f"파일 '{file['filename']}' 패치 내용 분석 (패치 길이: {len(file['patch'])}, 추출 코드 길이: {len(code_to_analyze)})")
               
            processed_count += 1
            tasks.append(self._enqueue_code_analysis(
                code_to_analyze, 
                file["filename"], 
                commit_sha, 
                user_id
            ))
        
        api_logger.info(f"총 {len(files)}개 파일 중 {processed_count}개 파일 분석 작업 등록됨")
        if tasks:
            await asyncio.gather(*tasks)
            api_logger.info("모든 코드 분석 작업이 큐에 추가됨")
        else:
            api_logger.warning("분석할 파일이 없습니다 - 큐에 작업이 추가되지 않음")
    
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
        api_logger.info(f"'{filename}' 코드 분할 시작 (길이: {len(code)})")
        chunks = self._split_code_if_needed(code)
        api_logger.info(f"'{filename}' 분할 결과: {len(chunks)}개 청크")
        
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
            api_logger.info(f"'{filename}' 청크 {i+1}/{len(chunks)} 큐에 추가됨 (길이: {len(chunk)})")
    
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
    
    async def process_queue(self):
        """비동기 큐 처리 - 실제로 종료되게 수정"""
        api_logger.info("코드 분석 큐 처리 시작")
        
        try:
            queue_size = self.queue.qsize()
            api_logger.info(f"현재 큐 크기: {queue_size}")
        except NotImplementedError:
            api_logger.info("큐 크기 확인 불가")
        
        # 무작정 대기하지 않고 작업이 있는 경우만 처리
        if self.queue.empty():
            api_logger.info("큐가 비어있음, 작업 없음")
            return
        
        # 현재 큐에 있는 항목만 처리하기 위해 개수 미리 저장
        try:
            items_to_process = self.queue.qsize()
        except NotImplementedError:
            # 큐 사이즈를 가져올 수 없으면 일단 한 개만 처리
            items_to_process = 1
        
        api_logger.info(f"처리할 항목 수: {items_to_process}")
        
        # 현재 있는 항목만 처리하고 종료
        for _ in range(items_to_process):
            if self.queue.empty():
                break
            
            try:
                # 큐에서 아이템 가져오기 (최대 3초 대기)
                try:
                    item = await asyncio.wait_for(self.queue.get(), timeout=3.0)
                except asyncio.TimeoutError:
                    api_logger.info("큐 대기 타임아웃, 작업 종료")
                    break
            
                # 아이템 처리
                try:
                    api_logger.info(f"아이템 처리: {item.get('filename', 'unknown')}")
                    # 참조 파일 가져오기 (필요한 경우)
                    await self._fetch_reference_files(item)
                    
                    # LLM API 호출 및 결과 저장
                    result = await self._call_llm_api(item)
                    await self._store_analysis_result(item, result)
                except Exception as e:
                    api_logger.error(f"처리 실패: {str(e)}")
                finally:
                    # 작업 완료 표시
                    self.queue.task_done()
            except Exception as e:
                api_logger.error(f"대기 중 오류: {str(e)}")
        
        api_logger.info("예정된 모든 작업 처리 완료")
    
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
    
    async def _call_llm_api(self, item: Dict) -> str:
        """LLM API 호출
        
        메타데이터 정보를 활용하여 연속된 청크의 경우 이전 요약 정보를 참조하여 컨텍스트 유지
        캐싱을 통해 동일 함수/클래스에 대한 중복 처리 방지
        """
        api_logger.info(f"LLM API 호출: {item['filename']} 청크 {item['chunk_index']+1}/{item['total_chunks']}")
        
        code = item['code']
        metadata = item.get('metadata', {})
        filename = item['filename']
        commit_sha = item['commit_sha']
        user_id = item['user_id']
        
        # 캐시 키 생성 (함수/클래스 이름 기반)
        cache_key = None
        if 'block_name' in metadata and 'block_type' in metadata:
            # 함수/클래스 단위로만 캐싱 (청크 번호 제외)
            block_name = metadata['block_name']
            block_type = metadata['block_type']
            cache_key = f"{user_id}:{filename}:{commit_sha}:{block_type}:{block_name}"
            
            # 연속된 청크인 경우 이전 함수 요약을 가져옴
            if 'is_continuation' in metadata and metadata['is_continuation']:
                previous_result = self.redis_client.get(cache_key)
                if previous_result:
                    api_logger.info(f"청크 분석 진행 중: {block_name} (이전 요약 있음)")
                    # 이 청크는 이미 분석 중인 함수의 일부이므로, LLM은 호출하되 캐시는 따로 저장하지 않음
                    # 최종 청크에서 전체 요약본을 저장할 것임
                    
                    # OpenAI API 파라미터 준비 (이전 요약 포함)
                    prompt = self._prepare_llm_prompt(code, metadata, previous_result, filename)
                    api_logger.info(f"이전 요약을 포함한 프롬프트 준비 완료 (길이: {len(prompt)})")
                    print(prompt)
                    
                    # TODO: 실제 OpenAI API 호출 구현
                    # 임시 구현
                    result = f"이전 요약을 참조한 분석: {previous_result[:30]}... - {block_name} 계속"
                    return result
        else:
            # 함수/클래스가 아닌 일반 코드는 인덱스로 캐싱
            cache_key = f"{user_id}:{filename}:{commit_sha}:{item['chunk_index']}"
        
        # Redis에서 캐시된 결과 확인
        cached_result = self.redis_client.get(cache_key)
        if cached_result:
            api_logger.info(f"캐시된 결과 사용: {cache_key}")
            return cached_result
        
        # OpenAI API 파라미터 준비
        prompt = self._prepare_llm_prompt(code, metadata, None, filename)
        api_logger.info(f"프롬프트 준비 완료 (길이: {len(prompt)})")
        
        # OpenAI API 호출 구현
        try:
            # OpenAI API를 이용한 코드 분석
            # 아래는 임시 구현으로, 실제 구현 시 OpenAI API 호출 코드로 대체해야 함
            api_logger.info("OpenAI API 호출 (임시 구현)")
            
            # 실제 OpenAI API 코드는 아래와 같이 구현할 수 있습니다:
            # from openai import AsyncOpenAI
            # client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            # response = await client.chat.completions.create(
            #     model="gpt-4",
            #     messages=[
            #         {"role": "system", "content": "You are a code analysis assistant."},
            #         {"role": "user", "content": prompt}
            #     ],
            #     temperature=0.3,
            #     max_tokens=1500
            # )
            # result = response.choices[0].message.content
            
            # 임시 결과 생성
            if 'block_name' in metadata:
                result = f"코드 분석 결과: {metadata['block_name']} in {filename}"
            else:
                result = f"코드 분석 결과: 일반 코드 in {filename}"
            
            api_logger.info(f"OpenAI API 응답 받음 (길이: {len(result)})")
            
        except Exception as e:
            api_logger.error(f"OpenAI API 호출 실패: {str(e)}")
            result = f"분석 실패: {str(e)}"
        
        # 함수/클래스 단위로만 캐싱 - 이 단계에서는 저장하지 않고 _store_analysis_result에서 처리
        # 여기서 캐싱하지 않는 이유는 연속된 청크의 경우 병합 처리가 필요하기 때문
        
        return result
    
    def _prepare_llm_prompt(self, code: str, metadata: Dict[str, Any], previous_summary: str = None, filename: str = "") -> str:
        """LLM API 호출을 위한 프롬프트 생성"""
        prompt_parts = []
        
        # 시스템 명령 추가
        prompt_parts.append("코드를 분석하고 요약해주세요. 다음 형식으로 응답하세요:")
        prompt_parts.append("1. 기능 요약: [한 문장 요약]")
        prompt_parts.append("2. 주요 로직: [핵심 로직 설명]")
        
        # 파일명 정보 추가
        prompt_parts.append(f"\n파일명: {filename}")
        
        # 이전 요약 정보가 있으면 추가
        if previous_summary:
            prompt_parts.append(f"\n이전 코드 요약: {previous_summary}")
            prompt_parts.append("이어지는 코드를 분석하세요.")
        
        # 메타데이터 정보 추가
        if 'block_type' in metadata and 'block_name' in metadata:
            prompt_parts.append(f"\n{metadata['block_type'].capitalize()}: {metadata['block_name']}")
        
        # 참조 파일 내용 있으면 추가
        if 'reference_file' in metadata:
            prompt_parts.append(f"\n참조 파일: {metadata['reference_file']}")
            
            if 'reference_content' in metadata:
                prompt_parts.append("\n참조 파일 내용:")
                # 참조 파일 내용이 너무 길면 적절히 잘라서 추가
                ref_content = metadata['reference_content']
                if len(ref_content) > 2000:  # 긴 참조 파일은 요약 또는 자르기
                    ref_content = ref_content[:2000] + "... (생략됨)"
                prompt_parts.append(ref_content)
            elif 'reference_error' in metadata:
                prompt_parts.append(f"\n참조 파일 오류: {metadata['reference_error']}")
        
        # 응답 형식 지정되어 있으면 추가
        if 'response_format' in metadata:
            prompt_parts.append(f"\n응답 형식: {metadata['response_format']}")
        
        # 요구사항 있으면 추가
        if 'requirements' in metadata:
            prompt_parts.append(f"\n요구사항: {metadata['requirements']}")
        
        # 일반 주석 있으면 추가
        if 'comment' in metadata:
            prompt_parts.append(f"\n주석: {metadata['comment']}")
        
        # 코드 추가
        prompt_parts.append("\n분석할 코드:")
        prompt_parts.append(code)
        
        # 추가 지시사항
        if 'has_next_chunk' in metadata and metadata['has_next_chunk']:
            prompt_parts.append("\n참고: 이 코드는 다음 청크에서 계속됩니다. 현재까지의 내용을 요약해주세요.")
        
        return "\n".join(prompt_parts)
    
    async def _store_analysis_result(self, item: Dict, result: str):
        """분석 결과 저장"""
        api_logger.info(f"분석 결과 저장: {item['filename']} 청크 {item['chunk_index']+1}")
        
        metadata = item.get('metadata', {})
        user_id = item['user_id']
        filename = item['filename']
        commit_sha = item['commit_sha']
        
        # 함수/클래스 기반 키 (있는 경우)
        block_key = None
        if 'block_name' in metadata and 'block_type' in metadata:
            block_name = metadata['block_name']
            block_type = metadata['block_type']
            
            # 함수/클래스 단위로만 저장 (청크 번호 제외)
            block_key = f"{user_id}:{filename}:{commit_sha}:{block_type}:{block_name}"
            
            # 여러 청크로 나뉜 경우에는 마지막 청크 결과만 저장하거나 
            # 이전 결과와 병합하여 함수 전체에 대한 요약으로 저장
            if 'is_continuation' in metadata and metadata['is_continuation']:
                # 이전 요약이 있으면 가져오기
                prev_result = self.redis_client.get(block_key)
                if prev_result:
                    # 이전 요약과 현재 요약 병합 (여기서는 간단히 연결)
                    combined_result = f"{prev_result}\n---\n{result}"
                    result = combined_result
                    api_logger.info(f"함수 요약 병합: {block_name}")
            
            # Redis에 함수/클래스 단위로만 저장
            self.redis_client.set(block_key, result, ex=86400)  # 24시간 유지
            api_logger.info(f"함수 단위로 저장됨: {block_key}")
        else:
            # 함수/클래스가 아닌 일반 코드는 인덱스로 저장
            index_key = f"{user_id}:{filename}:{commit_sha}:{item['chunk_index']}"
            self.redis_client.set(index_key, result, ex=86400)  # 24시간 유지
        
        # Supabase에 결과 저장 (실제 구현)
        try:
            # 분석 결과 데이터 준비
            analysis_data = {
                "user_id": user_id,
                "filename": filename,
                "commit_sha": commit_sha,
                "chunk_index": item['chunk_index'],
                "total_chunks": item['total_chunks'],
                "result": result,
                "metadata": metadata
            }
            
            # 함수/클래스 정보가 있으면 추가
            if 'block_name' in metadata:
                analysis_data["block_name"] = metadata['block_name']
                analysis_data["block_type"] = metadata['block_type']
                
                if 'is_continuation' in metadata:
                    analysis_data["is_continuation"] = True
                    analysis_data["previous_chunk"] = metadata['previous_chunk']
            
            # Supabase에 저장 아직 이부분은 없음
            table_name = "code_analysis_results"
            await self.supabase.table(table_name).insert(analysis_data).execute()
            api_logger.info(f"Supabase에 분석 결과 저장 완료: {filename}, 청크 {item['chunk_index']+1}")
            
        except Exception as e:
            api_logger.error(f"Supabase 저장 실패: {str(e)}")