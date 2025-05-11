import hashlib
import secrets
import time
from typing import Dict, Optional, List
from supabase._async.client import AsyncClient
from app.utils.logger import api_logger
from app.services.supa_auth_service import (
    create_user_api_key, 
    get_user_by_key_hash, 
    get_user_api_keys, 
    delete_user_api_key
)

async def generate_api_key(user_id: str, supabase: AsyncClient) -> str:
    """
    사용자를 위한 새 API 키 생성
    
    비즈니스 로직:
    1. 고유한 API 키 생성 (prefix + timestamp + random string)
    2. 키를 해시하여 저장
    3. 원본 키는 사용자에게 반환 (이후 복구 불가)
    """
    try:
        # API 키 생성 로직
        prefix = "stdy_"
        timestamp = hex(int(time.time()))[2:]
        random_part = secrets.token_urlsafe(24)
        
        full_key = f"{prefix}{timestamp}_{random_part}"
        hashed_key = hashlib.sha256(full_key.encode()).hexdigest()
        
        # DB 레이어 함수 호출
        result = await create_user_api_key(prefix, hashed_key, user_id, supabase)
        
        if not result or not result.data:
            api_logger.error(f"API 키 생성 후 DB 저장 실패: {user_id}")
            return None
            
        return full_key
    except Exception as e:
        api_logger.error(f"API 키 생성 실패: {str(e)}")
        return None

async def verify_api_key(api_key: str, supabase: AsyncClient) -> bool:
    """
    API 키 검증 및 사용자 정보 반환
    
    비즈니스 로직:
    1. 입력된 API 키를 해시
    2. 해시된 키로 사용자 검색
    3. 유효한 키면 사용자 정보 반환, 아니면 None 반환
    """
    try:
        if not api_key:
            return False
            
        # 키 해시
        hashed_key = hashlib.sha256(api_key.encode()).hexdigest()
        
        # DB 레이어 함수 호출
        res = await get_user_by_key_hash(hashed_key, supabase)
        
        if not res or not res.data:
            return False
        
        return True
    except Exception as e:
        api_logger.error(f"API 키 검증 실패: {str(e)}")
        return False

async def get_masked_keys(user_id: str, supabase: AsyncClient) -> List[Dict]:
    """
    사용자의 모든 API 키 목록 조회 (마스킹 처리)
    
    비즈니스 로직:
    1. 사용자 ID로 모든 활성 API 키 조회
    2. 보안을 위해 키를 마스킹 처리하여 반환
    """
    try:
        # DB 레이어 함수 호출
        res = await get_user_api_keys(user_id, supabase)
        
        if not res or not res.data:
            return []
        
        # 접두어 기반 마스킹 처리 (비즈니스 로직)
        keys = []
        for key in res.data:
            masked_key = f"{key['api_key_prefix']}****-****-****"
            keys.append({
                "id": key["id"],
                "masked_key": masked_key,
                "created_at": key["created_at"]
            })
        
        return keys
    except Exception as e:
        api_logger.error(f"마스킹된 API 키 목록 조회 실패: {str(e)}")
        return []

async def revoke_api_key(key_id: str, user_id: str, supabase: AsyncClient) -> bool:
    """
    API 키 비활성화
    
    비즈니스 로직:
    1. 키 ID와 사용자 ID로 해당 키 비활성화
    2. 성공 여부 반환
    """
    try:
        # DB 레이어 함수 호출
        res = await delete_user_api_key(key_id, user_id, supabase)
        
        return res and bool(res.data)
    except Exception as e:
        api_logger.error(f"API 키 비활성화 실패: {str(e)}")
        return False