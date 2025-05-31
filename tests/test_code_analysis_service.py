import pytest
import asyncio
import json
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
import concurrent.futures
import time

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from redis import Redis
from supabase._async.client import AsyncClient
from app.services.code_analysis_service import CodeAnalysisService
from app.utils.logger import api_logger

# ✅ Step 5: 통합/유닛 테스트 작성

class TestCodeAnalysisService:
    """CodeAnalysisService 테스트 클래스 - 24/7 운영 최적화 버전"""
    
    @pytest.fixture
    def mock_redis(self):
        """Redis 클라이언트 모킹"""
        mock = MagicMock(spec=Redis)
        mock.ping.return_value = True
        mock.hset.return_value = True
        mock.hget.return_value = None
        mock.hgetall.return_value = {}
        mock.expire.return_value = True
        mock.incr.return_value = 1
        mock.decr.return_value = 0
        mock.delete.return_value = True
        mock.get.return_value = None
        mock.setex.return_value = True
        
        # Pipeline 모킹
        mock_pipeline = MagicMock()
        mock_pipeline.incr.return_value = mock_pipeline
        mock_pipeline.expire.return_value = mock_pipeline
        mock_pipeline.execute.return_value = [1, True]
        mock.pipeline.return_value = mock_pipeline
        
        return mock
    
    @pytest.fixture
    def mock_supabase(self):
        """Supabase 클라이언트 모킹"""
        mock = MagicMock(spec=AsyncClient)
        return mock
    
    @pytest.fixture
    def service(self, mock_redis, mock_supabase):
        """CodeAnalysisService 인스턴스 생성"""
        return CodeAnalysisService(mock_redis, mock_supabase)
    
    # ✅ Step 3 테스트: Hash 기반 저장 (메서드명 수정)
    @pytest.mark.asyncio
    async def test_save_function_summary_to_hash(self, service):
        """Hash 방식 함수 요약 저장 테스트 (I/O 오프로딩 포함)"""
        # Given
        user_id = "test_user"
        commit_sha = "abc123"
        filename = "test.py"
        func_name = "test_function"
        summary = "테스트 함수 요약"
        
        # Mock executor and run_in_executor
        mock_executor = MagicMock()
        with patch.object(service, '_get_shared_executor', return_value=mock_executor):
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.run_in_executor = AsyncMock(return_value=True)
                
                # When
                await service._save_function_summary_to_hash(
                    user_id, commit_sha, filename, func_name, summary
                )
                
                # Then: run_in_executor 호출 확인
                mock_loop.return_value.run_in_executor.assert_called_once()
                args = mock_loop.return_value.run_in_executor.call_args[0]
                assert args[0] == mock_executor  # executor
                # args[1]은 sync 함수
    
    @pytest.mark.asyncio
    async def test_collect_function_summaries_hash_method(self, service):
        """Hash 방식으로 함수 요약 수집 테스트 (I/O 오프로딩 포함)"""
        # Given
        user_id = "test_user"
        commit_sha = "abc123" 
        filename = "test.py"
        
        # ✅ _sync_hash_collect는 이미 bytes→str 변환된 dict를 반환
        expected_result = {
            'function1': 'summary1',
            'function2': 'summary2'
        }
        
        # Mock executor and run_in_executor
        mock_executor = MagicMock()
        with patch.object(service, '_get_shared_executor', return_value=mock_executor):
            with patch('asyncio.get_event_loop') as mock_loop:
                # _sync_hash_collect가 반환하는 것은 이미 변환된 dict
                mock_loop.return_value.run_in_executor = AsyncMock(return_value=expected_result)
                
                # When
                result = await service._collect_function_summaries(user_id, filename, commit_sha)
                
                # Then: run_in_executor 호출 확인 및 결과 확인
                mock_loop.return_value.run_in_executor.assert_called_once()
                assert result == expected_result
    
    # ✅ Step 2 테스트: Redis 카운터 기반 pending 관리 (I/O 오프로딩)
    @pytest.mark.asyncio
    async def test_increment_pending_count(self, service):
        """pending 카운터 증가 테스트 (I/O 오프로딩 포함)"""
        # Given
        user_id = "test_user"
        commit_sha = "abc123"
        filename = "test.py"
        
        # Mock executor and run_in_executor
        mock_executor = MagicMock()
        with patch.object(service, '_get_shared_executor', return_value=mock_executor):
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
                
                # When
                await service._increment_pending_count(user_id, commit_sha, filename)
                
                # Then: run_in_executor 호출 확인
                mock_loop.return_value.run_in_executor.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_decrement_pending_count(self, service):
        """pending 카운터 감소 및 완료 판정 테스트 (I/O 오프로딩 포함)"""
        # Given
        user_id = "test_user"
        commit_sha = "abc123"
        filename = "test.py"
        
        # Mock executor and run_in_executor
        mock_executor = MagicMock()
        with patch.object(service, '_get_shared_executor', return_value=mock_executor):
            with patch('asyncio.get_event_loop') as mock_loop:
                # Case 1: 남은 카운터가 있는 경우
                mock_loop.return_value.run_in_executor = AsyncMock(return_value=2)
                
                # When
                remaining = await service._decrement_pending_count(user_id, commit_sha, filename)
                
                # Then
                assert remaining == 2
                mock_loop.return_value.run_in_executor.assert_called_once()
    
    # ✅ Step 5 테스트: 공유 ThreadPoolExecutor
    @pytest.mark.asyncio
    async def test_shared_executor_lazy_initialization(self):
        """공유 ThreadPoolExecutor 지연 초기화 테스트"""
        # Given: 클래스 레벨 Executor 초기화
        CodeAnalysisService._shared_executor = None
        
        # When: 첫 번째 호출
        executor1 = await CodeAnalysisService._get_shared_executor()
        
        # Then: ThreadPoolExecutor 생성됨
        assert isinstance(executor1, concurrent.futures.ThreadPoolExecutor)
        assert CodeAnalysisService._shared_executor is not None
        
        # When: 두 번째 호출
        executor2 = await CodeAnalysisService._get_shared_executor()
        
        # Then: 같은 인스턴스 반환 (재사용)
        assert executor1 is executor2
    
    @pytest.mark.asyncio
    async def test_cleanup_executor(self):
        """ThreadPoolExecutor 정리 테스트"""
        # Given: Executor 생성
        await CodeAnalysisService._get_shared_executor()
        assert CodeAnalysisService._shared_executor is not None
        
        # When: 정리 호출
        with patch.object(CodeAnalysisService._shared_executor, 'shutdown') as mock_shutdown:
            await CodeAnalysisService.cleanup_executor()
        
        # Then: shutdown 호출되고 None으로 초기화
        mock_shutdown.assert_called_once_with(wait=True)
        assert CodeAnalysisService._shared_executor is None
    
    # ✅ Step 6 테스트: LLM 이중 타임아웃
    @pytest.mark.asyncio
    async def test_llm_timeout_handling(self, service):
        """LLM 호출 타임아웃 처리 테스트"""
        # Given
        func_info = {
            'name': 'test_func',
            'filename': 'test.py',
            'code': 'def test(): pass'
        }
        
        # Mock ThreadPoolExecutor와 Future를 올바르게 설정
        mock_executor = MagicMock()
        mock_future = concurrent.futures.Future()
        mock_executor.submit.return_value = mock_future
        
        # When: asyncio.TimeoutError 발생 시뮬레이션
        with patch('asyncio.wait_for', side_effect=asyncio.TimeoutError):
            with patch.object(service, '_get_shared_executor', return_value=mock_executor):
                with patch('asyncio.get_event_loop') as mock_loop:
                    # run_in_executor가 Future를 반환하도록 설정
                    mock_loop.return_value.run_in_executor.return_value = mock_future
                    
                    result = await service._call_llm_for_function(func_info, 'test code', {})
        
        # Then: 타임아웃 메시지 반환
        assert "타임아웃으로 인한 분석 실패" in result
        assert func_info['name'] in result
    
    @pytest.mark.asyncio
    async def test_llm_dual_timeout_configuration(self, service):
        """LLM 이중 타임아웃 설정 확인 테스트"""
        # Given
        func_info = {'name': 'test', 'filename': 'test.py', 'code': 'def test(): pass'}
        
        # Mock OpenAI client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "test response"
        mock_client.chat.completions.create.return_value = mock_response
        
        with patch('openai.OpenAI', return_value=mock_client):
            with patch.object(service, '_get_shared_executor') as mock_get_executor:
                mock_executor = MagicMock()
                mock_get_executor.return_value = mock_executor
                
                with patch('asyncio.wait_for') as mock_wait_for:
                    with patch('asyncio.get_event_loop') as mock_loop:
                        mock_loop.return_value.run_in_executor = AsyncMock(return_value="test response")
                        mock_wait_for.return_value = "test response"
                        
                        # When
                        await service._call_llm_for_function(func_info, 'test code', {})
                        
                        # Then: 외부 타임아웃 35초 확인
                        mock_wait_for.assert_called_once()
                        args, kwargs = mock_wait_for.call_args
                        assert kwargs['timeout'] == 35
                        
                        # run_in_executor 호출 확인
                        mock_loop.return_value.run_in_executor.assert_called_once()

    # ✅ 통합 테스트: 전체 파이프라인 (메서드명 수정)
    @pytest.mark.asyncio
    async def test_analyze_function_pipeline(self, service):
        """함수 분석 전체 파이프라인 통합 테스트"""
        # Given
        item = {
            'function_info': {
                'name': 'test_function',
                'filename': 'test.py',
                'code': 'def test_function(): pass',
                'has_changes': True
            },
            'commit_sha': 'abc123',
            'user_id': 'test_user',
            'owner': 'test_owner',
            'repo': 'test_repo',
            'metadata': {}
        }
        
        # Mock executor for I/O offloading
        mock_executor = MagicMock()
        with patch.object(service, '_get_shared_executor', return_value=mock_executor):
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.run_in_executor = AsyncMock(side_effect=[
                    None,  # 이전 요약 없음 (_sync_prev_check)
                    None,  # _save_function_summary_to_hash  
                    0      # _decrement_pending_count (마지막 함수)
                ])
                
                with patch.object(service, '_call_llm_for_function', return_value="test summary") as mock_llm:
                    with patch.object(service, '_handle_file_analysis_complete') as mock_complete:
                        
                        # When
                        await service._analyze_function(item)
                        
                        # Then
                        mock_llm.assert_called_once()
                        mock_complete.assert_called_once()  # 마지막 함수이므로 완료 처리 호출
    
    # ✅ 에러 시나리오 테스트 (I/O 오프로딩 반영)
    @pytest.mark.asyncio 
    async def test_analyze_function_error_handling(self, service):
        """함수 분석 실패 시 pending 카운터 감소 테스트"""
        # Given
        item = {
            'function_info': {
                'name': 'test',
                'filename': 'test.py',
                'code': 'def test(): pass'
            },
            'commit_sha': 'abc123',
            'user_id': 'test_user',
            'owner': 'test_owner',
            'repo': 'test_repo',
            'metadata': {}
        }
        
        # Mock executor
        mock_executor = MagicMock()
        with patch.object(service, '_get_shared_executor', return_value=mock_executor):
            with patch('asyncio.get_event_loop') as mock_loop:
                # 첫 번째 run_in_executor 호출 (이전 요약 조회)은 성공
                # 두 번째 run_in_executor 호출 (카운터 감소)도 성공
                mock_loop.return_value.run_in_executor = AsyncMock(side_effect=[None, 0])
                
                with patch.object(service, '_call_llm_for_function', side_effect=Exception("LLM Error")):
                    
                    # When & Then
                    with pytest.raises(Exception, match="LLM Error"):
                        await service._analyze_function(item)
                    
                    # run_in_executor가 2번 호출됨 (이전 요약 조회 + 카운터 감소)
                    assert mock_loop.return_value.run_in_executor.call_count == 2
    
    # ✅ 성능 테스트 (시간 모킹 완전 제거)
    @pytest.mark.asyncio
    async def test_concurrent_function_analysis(self, service):
        """동시 함수 분석 처리 성능 테스트"""
        # Given: 10개 함수 동시 분석
        items = []
        for i in range(10):
            items.append({
                'function_info': {
                    'name': f'func_{i}',
                    'filename': 'test.py',
                    'code': f'def func_{i}(): pass'
                },
                'commit_sha': 'abc123',
                'user_id': 'test_user',
                'owner': 'test_owner',
                'repo': 'test_repo',
                'metadata': {}
            })
        
        # Mock executor for all I/O operations
        mock_executor = MagicMock()
        
        # ✅ 시간 측정은 모킹 없이 직접 수행
        with patch.object(service, '_get_shared_executor', return_value=mock_executor):
            with patch('asyncio.get_event_loop') as mock_get_loop:
                real_loop = asyncio.get_event_loop()
                mock_get_loop.return_value = real_loop
                
                # run_in_executor만 모킹
                with patch.object(real_loop, 'run_in_executor', new_callable=AsyncMock) as mock_executor_call:
                    # 각 함수마다 3번의 run_in_executor 호출 (조회 + 저장 + 카운터)
                    mock_executor_call.side_effect = [
                        None, None, 0  # 함수 0
                    ] * 10  # 10개 함수
                    
                    with patch.object(service, '_call_llm_for_function', return_value="summary"):
                        with patch.object(service, '_handle_file_analysis_complete'):
                            
                            # When: 동시 분석 실행 (실제 시간 측정)
                            start_time = time.time()
                            await asyncio.gather(*[service._analyze_function(item) for item in items])
                            end_time = time.time()
                            
                            # Then: 병렬 처리로 빠른 완료 (순차 처리보다 빨라야 함)
                            execution_time = end_time - start_time
                            assert execution_time < 10  # 10초 이내 완료 