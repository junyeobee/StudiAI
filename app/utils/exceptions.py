from fastapi import HTTPException
from app.utils.logger import api_logger

def handle_exception(e: Exception) -> None:
    """예외를 처리하고 적절한 HTTP 응답을 반환합니다."""
    api_logger.error(f"Error occurred: {str(e)}")
    if isinstance(e, HTTPException):
        raise e
    raise HTTPException(status_code=500, detail=str(e)) 