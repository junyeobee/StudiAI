"""
PY_ASYNC_01 테스트용 - 비동기 함수들
"""
import asyncio
import httpx

async def fetch_data(url: str) -> dict:
    """비동기 데이터 가져오기"""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()

async def process_data(data: list) -> list:
    """비동기 데이터 처리"""
    tasks = [asyncio.create_task(process_item(item)) for item in data]
    return await asyncio.gather(*tasks)

async def process_item(item: dict) -> dict:
    """개별 아이템 처리"""
    await asyncio.sleep(0.1)  # 시뮬레이션
    return {"processed": item}

def sync_helper() -> str:
    """동기 헬퍼 함수"""
    return "helper result" 