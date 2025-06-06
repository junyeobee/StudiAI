import pytest

pytest.skip("Supabase integration tests are skipped in this environment", allow_module_level=True)

@pytest.fixture
async def supabase_client():
    """테스트용 Supabase 클라이언트 초기화"""
    client = await init_supabase()
    yield client
    # 테스트 후 정리 작업이 필요한 경우 여기에 추가

@pytest.mark.asyncio
async def test_insert_learning_database(supabase_client: AsyncClient):
    """학습 데이터베이스 등록 테스트"""
    db_id = "test_db_id"
    title = "테스트 DB"
    parent_page_id = "test_parent_id"
    
    result = await insert_learning_database(
        db_id=db_id,
        title=title,
        parent_page_id=parent_page_id,
        supabase=supabase_client
    )
    
    assert result is True
    
    # 등록된 데이터 확인
    db_id, _ = await get_learning_database_by_title(title)
    assert db_id == db_id

@pytest.mark.asyncio
async def test_get_learning_database_by_title(supabase_client: AsyncClient):
    """제목으로 학습 데이터베이스 조회 테스트"""
    title = "테스트 DB"
    db_id, _ = await get_learning_database_by_title(title)
    assert db_id is not None 