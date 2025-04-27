"""
API 요청 재시도 유틸리티
"""
import asyncio
from typing import Callable, Any, Type
from functools import wraps
from app.utils.logger import api_logger

def async_retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,)
) -> Callable:
    """
    비동기 함수에 대한 재시도 데코레이터
    
    Args:
        max_retries: 최대 재시도 횟수
        delay: 초기 지연 시간 (초)
        backoff: 지연 시간 증가 계수
        exceptions: 재시도할 예외 타입
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        api_logger.warning(
                            f"Attempt {attempt + 1} failed: {str(e)}. "
                            f"Retrying in {current_delay} seconds..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        api_logger.error(
                            f"All {max_retries} attempts failed. Last error: {str(e)}"
                        )
                        raise last_exception
            
            raise last_exception
        return wrapper
    return decorator 