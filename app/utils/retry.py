"""
API 요청 재시도 유틸리티
"""
import asyncio
from typing import Callable, Any, Type
from functools import wraps
from app.utils.logger import api_logger
import httpx

def async_retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0, exceptions: tuple[Type[Exception], ...] = (Exception,)) -> Callable:
    """
    API 요청 재시도 데코레이터
    
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
                    
                    # 예외 정보를 안전하게 추출
                    error_msg = str(e)
                    if hasattr(e, 'response') and e.response is not None:
                        try:
                            error_msg = f"{e.__class__.__name__}: {e.response.status_code} - {e.response.text}"
                        except Exception:
                            error_msg = f"{e.__class__.__name__}: {str(e)}"
                    else:
                        error_msg = f"{e.__class__.__name__}: {str(e)}"
                    
                    if attempt < max_retries - 1:
                        api_logger.warning(
                            f"Attempt {attempt + 1} failed: {error_msg}. "
                            f"Retrying in {current_delay} seconds..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        api_logger.error(
                            f"All {max_retries} attempts failed. Last error: {error_msg}"
                        )
                        raise last_exception
            
            raise last_exception
        return wrapper
    return decorator 