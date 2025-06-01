"""
PY_DECORATOR_01 테스트용 - 데코레이터가 있는 함수들
"""
from fastapi import APIRouter, Depends
from functools import wraps

router = APIRouter()

def my_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

@router.get("/pages")
async def list_learning_pages(current: bool = False):
    """학습 페이지 목록 조회"""
    return {"pages": []}

@router.post("/pages/create") 
@my_decorator
async def create_pages(data: dict):
    """학습 페이지 생성"""
    return {"status": "success"}

class Baz:
    """테스트 클래스"""
    
    @property
    def qux(self):
        """프로퍼티 메서드"""
        return "qux_value"
    
    @staticmethod
    def static_method():
        """정적 메서드"""
        return "static" 