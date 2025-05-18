"""
Custom exceptions for the application
"""
from fastapi import HTTPException, status

class NotionAPIError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Notion API Error: {detail}"
        )

class DatabaseError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database Error: {detail}"
        )

class WebhookError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook Error: {detail}"
        )

class NotFoundError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Not Found Error: {detail}"
        )

class ValidationError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Validation Error: {detail}"
        )

class LearningError(Exception):
    """학습 관련 예외 클래스"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message) 

class RedisError(Exception):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Redis Error: {detail}"
        )

class GithubAPIError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Github API Error: {detail}"
        )
