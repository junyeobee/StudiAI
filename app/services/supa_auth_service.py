from app.utils.logger import api_logger
from supabase._async.client import AsyncClient
from datetime import datetime
from typing import List, Dict, Optional
from app.core.exceptions import DatabaseError
from app.models.auth import UserIntegration, UserIntegrationResponse

async def get_user_by_key_hash(hashed_key: str, supabase: AsyncClient):
    """해시된 API 키로 유저 조회"""
    try:
        res = await supabase.table("mcp_users") \
                         .select("user_id") \
                         .eq("auth_token", hashed_key) \
                         .execute()
        return res
    except Exception as e:
        api_logger.error(f"유저 조회 실패: {str(e)}")
        raise DatabaseError(e)

async def create_user_api_key(prefix: str, hashed_key: str, user_id: str, supabase: AsyncClient):
    """사용자 API 키 정보 저장"""
    try:
        res = await supabase.table("mcp_users").upsert({
            "user_id": user_id,
            "api_key_prefix": prefix,
            "auth_token": hashed_key,
            "created_at": datetime.now().isoformat(),
            "status": "active"
        }).execute()
        return res
    except Exception as e:
        api_logger.error(f"사용자 API 키 생성 실패: {str(e)}")
        raise DatabaseError(e)

async def get_user_api_keys(user_id: str, supabase: AsyncClient):
    """유저 아이디로 API 키 목록 조회"""
    try:
        res = await supabase.table("mcp_users")\
                .select("id, auth_token, created_at")\
                .eq("user_id", user_id)\
                .eq("status", "active")\
                .execute()
        return res
    except Exception as e:
        api_logger.error(f"API 키 목록 조회 실패: {str(e)}")
        raise DatabaseError(e)

async def delete_user_api_key(key_id: str, user_id: str, supabase: AsyncClient):
    """API 키 비활성화"""
    try:
        res = await supabase.table("mcp_users")\
            .update({"status": "revoked", "updated_at": datetime.now().isoformat()})\
            .eq("id", key_id)\
            .eq("user_id", user_id)\
            .execute()
        return res
    except Exception as e:
        api_logger.error(f"API 키 비활성화 실패: {str(e)}")
        raise DatabaseError(e)
    
async def get_integrations_by_user_id(user_id:str, supabase:AsyncClient) -> List[Dict]:
    """
    사용자의 모든 통합 정보 조회
    """
    try:
        res = await supabase.table("user_integrations")\
            .select("*").eq("user_id", user_id).execute()
        return res.data
    except Exception as e:
        api_logger.error(f"사용자 통합 정보 조회 실패: {str(e)}")
        raise DatabaseError(e)

async def get_integration_by_id(user_id: str, provider: str, supabase: AsyncClient) -> Optional[dict]:
    """
    ID,로 통합 정보 조회
    """
    try:
        res = await supabase.table("user_integrations") \
            .select("*") \
            .eq("user_id", user_id) \
            .eq("provider", provider) \
            .single() \
            .execute()
        if res and res.data:
            return res.data
        return None
    except Exception as e:
        api_logger.error(f"통합 정보 조회 실패: {str(e)}")
        raise DatabaseError(e)

async def save_integration_token(request:UserIntegration, supabase:AsyncClient) -> UserIntegrationResponse:
    """
    통합 토큰 저장(처음 생성시 : id None, 업데이트시 : id 포함)
    """
    try:
        data_dict = request.model_dump()
        
        if 'id' in data_dict and data_dict['id'] is None:
            del data_dict['id']
        
        for field in ['created_at', 'updated_at', 'expires_at']:
            if field in data_dict and data_dict[field] is not None and isinstance(data_dict[field], datetime):
                data_dict[field] = data_dict[field].isoformat()
                
        res = await supabase.table("user_integrations") \
            .upsert(data_dict) \
            .execute()
        return res.data[0]
    except Exception as e:
        api_logger.error(f"통합 토큰 저장 실패: {str(e)}")
        raise DatabaseError(e)
    

