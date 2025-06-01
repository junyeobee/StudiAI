"""
PY_BASIC_01 테스트용 - 기본 함수들
"""
import os
from typing import List

def foo(x: int) -> int:
    """간단한 함수"""
    return x * 2

def bar(name: str, age: int = 25) -> str:
    """매개변수가 있는 함수"""
    return f"Hello {name}, you are {age} years old"

def process_list(items: List[str]) -> List[str]:
    """리스트 처리 함수"""
    return [item.upper() for item in items] 