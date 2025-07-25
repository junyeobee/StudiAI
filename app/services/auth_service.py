import hashlib
import secrets
import time
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
from supabase._async.client import AsyncClient
from app.utils.logger import api_logger
from app.core.exceptions import DatabaseError, ValidationError
from app.services.supa_auth_service import (
    create_user_api_key, 
    get_user_by_key_hash_async, 
    get_user_api_keys, 
    delete_user_api_key,
    get_integrations_by_user_id,
    get_integration_by_id,
    save_integration_token,
    get_user_workspaces,
    set_user_workspace
)
import base64
from app.models.auth import UserIntegrationRequest, UserIntegrationResponse, UserIntegration
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from app.core.config import settings
from app.services.OAuth_service import OAuthService
from app.models.notion_workspace import UserWorkspace, UserWorkspaceList

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
            raise DatabaseError(f"API 키 생성 후 DB 저장 실패: {user_id}")
            
        return full_key
    except DatabaseError:
        raise
    except Exception as e:
        api_logger.error(f"API 키 생성 실패: {str(e)}")
        raise DatabaseError(f"API 키 생성 실패: {str(e)}")

async def verify_api_key(api_key: str, supabase: AsyncClient) -> str:
    """
    API 키 검증 및 사용자 정보 반환
    
    비즈니스 로직:
    1. 입력된 API 키를 해시
    2. 해시된 키로 사용자 검색
    3. 유효한 키면 사용자 정보 반환, 아니면 None 반환
    """
    try:
        if not api_key:
            return None
            
        # 키 해시
        hashed_key = hashlib.sha256(api_key.encode()).hexdigest()
        
        # DB 레이어 함수 호출
        res = await get_user_by_key_hash_async(hashed_key, supabase)
        
        if not res or not res.data:
            return None
        
        return res.data[0]["user_id"]
    except Exception as e:
        api_logger.error(f"API 키 검증 실패: {str(e)}")
        raise DatabaseError(f"API 키 검증 실패: {str(e)}")

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
        raise DatabaseError(f"마스킹된 API 키 목록 조회 실패: {str(e)}")

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
        raise DatabaseError(f"API 키 비활성화 실패: {str(e)}")
    

async def get_user_integrations(user_id:str, supabase:AsyncClient) -> List[Dict]:
    """
    사용자의 모든 통합 정보 조회
    """
    try:
        return await get_integrations_by_user_id(user_id, supabase)
    except Exception as e:
        api_logger.error(f"사용자 통합 정보 조회 실패: {str(e)}")
        raise DatabaseError(f"사용자 통합 정보 조회 실패: {str(e)}")
    
async def encrypt_token(user_id:str,request: UserIntegrationRequest,supabase: AsyncClient) -> UserIntegrationResponse:
    """
    AES 암호화 키를 사용하여 통합 토큰을 암호화 후 저장
    """
    try:
        encryption_key = base64.b64decode(settings.ENCRYPTION_KEY)
        iv = get_random_bytes(16)
        cipher = AES.new(encryption_key, AES.MODE_GCM, nonce=iv)
        encrypted_access_token, tag_a = cipher.encrypt_and_digest(request.access_token.encode('utf-8'))
        token_store_value = base64.b64encode(encrypted_access_token + tag_a).decode('utf-8')
        encrypted_refresh_token = None
        if request.refresh_token:
            cipher = AES.new(encryption_key, AES.MODE_GCM, nonce=iv)
            encrypted_rt, tag_r = cipher.encrypt_and_digest(request.refresh_token.encode('utf-8'))
            encrypted_refresh_token = base64.b64encode(encrypted_rt + tag_r).decode('utf-8')
            
        iv_b64 = base64.b64encode(iv).decode('utf-8')
        
        expires_at = None
        if request.expires_in:
            expires_at = datetime.now() + timedelta(seconds=request.expires_in)

        integration_data = {
            "id": request.id if request.id else None,
            "user_id": user_id,
            "provider": request.provider,
            "access_token": token_store_value,
            "refresh_token": encrypted_refresh_token,
            "scopes": request.scopes,
            "created_at": request.created_at if request.created_at else datetime.now().isoformat(),
            "expires_at": expires_at.isoformat() if expires_at else None,
            "updated_at": datetime.now().isoformat(),
            "token_iv": iv_b64
        }
        
        integration_request = UserIntegration(**integration_data)

        return await save_integration_token(integration_request, supabase)
            
    except ValueError as e:
        api_logger.error(f"통합 정보 입력값 오류: {str(e)}")
        raise ValidationError(f"통합 정보 처리 오류: {str(e)}")
    except Exception as e:
        api_logger.error(f"통합 정보 암호화 실패: {str(e)}")
        raise DatabaseError(f"통합 정보 암호화 실패: {str(e)}")


async def get_integration_token(user_id: str,provider: str,supabase: AsyncClient) -> str:
    """
    저장된 통합 토큰을 복호화하여 가져옴
    
    Args:
        user_id: 사용자 식별자
        provider: 서비스 제공자 (github, notion 등)
        supabase: Supabase 클라이언트
    
    Returns:
        복호화된 접근 토큰
    """
    try:
        # DB에서 암호화된 토큰과 IV 조회
        res = await get_integration_by_id(user_id, provider, supabase)   
        if not res:
            return None
        # 암호화 키와 저장된 IV 가져오기
        encryption_key = base64.b64decode(settings.ENCRYPTION_KEY)
        iv = base64.b64decode(res["token_iv"])
        
        # 암호화된 토큰 및 태그 디코딩
        token_data = base64.b64decode(res["access_token"])
        encrypted_token = token_data[:-16]
        tag = token_data[-16:]
        
        # 복호화
        cipher = AES.new(encryption_key, AES.MODE_GCM, nonce=iv)
        decrypted_token = cipher.decrypt_and_verify(encrypted_token, tag).decode('utf-8')
        return decrypted_token
        
    except Exception as e:
        api_logger.error(f"토큰 복호화 실패: {str(e)}")
        raise ValidationError(f"토큰 복호화 실패: {str(e)}")

async def verify_integration_token(user_id: str,provider: str,token_to_verify: str,supabase: AsyncClient) -> bool:
    """
    사용자가 제공한 토큰을 검증
    
    Args:
        user_id: 사용자 식별자
        provider: 서비스 제공자 (github, notion 등)
        token_to_verify: 검증할 토큰
        supabase: Supabase 클라이언트
    
    Returns:
        토큰이 유효한지 여부
    """
    try:
        # 저장된 토큰 정보 조회
        res = await get_integration_by_id(user_id, provider, supabase)
            
        if not res:
            return False
        
        # 저장된 정보에서 해시된 토큰 복호화
        token_data = base64.b64decode(res["access_token"])
        encrypted_token = token_data[:-16]
        tag = token_data[-16:]
        encryption_key = base64.b64decode(settings.ENCRYPTION_KEY)
        iv = base64.b64decode(res["token_iv"])
        # 복호화
        cipher = AES.new(encryption_key, AES.MODE_GCM, nonce=iv)
        decrypted_token = cipher.decrypt_and_verify(encrypted_token, tag).decode('utf-8')
        
        
        # 해시값 비교
        return decrypted_token == token_to_verify
        
    except Exception as e:
        api_logger.error(f"토큰 검증 실패: {str(e)}")
        raise ValidationError(f"토큰 검증 실패: {str(e)}")

def parse_oauth_state(state: str) -> tuple:
    """
    OAuth state 파라미터 파싱
    
    Args:
        state: OAuth 콜백으로 전달된 state 문자열
        
    Returns:
        (user_id, state_uuid) 튜플
    """
    user_id, state_uuid = None, None
    if state:
        state_parts = state.split("|")
        for part in state_parts:
            if part.startswith("user_id="):
                user_id = part.split("user_id=")[1]
            elif part.startswith("uuid="):
                state_uuid = part.split("uuid=")[1]
    return user_id, state_uuid

async def process_notion_oauth(user_id: str, code: str, supabase: AsyncClient) -> dict:
    """
    Notion OAuth 코드 교환 및 토큰 저장
    
    Args:
        user_id: 사용자 ID
        code: OAuth 인증 코드
        supabase: Supabase 클라이언트
        
    Returns:
        처리 결과 딕셔너리
    """
    try:
        # 1. 토큰 교환
        oauth_service = OAuthService()
        token_data = await oauth_service.exchange_notion_code(code)
        
        # 2. 워크스페이스 정보 추출
        workspace_id = token_data["workspace_id"]
        
        # 3. 워크스페이스 저장
        user_workspace = UserWorkspace(
            user_id=user_id,
            workspace_id=token_data["workspace_id"],
            workspace_name=token_data["workspace_name"],
            provider="notion",
            status='inactive'
        )
        workspaces_list = UserWorkspaceList(workspaces=[user_workspace])
        await set_user_workspace(workspaces_list, supabase)
        
        # 4. 토큰 저장
        integration_data = await get_integration_by_id(user_id, "notion", supabase)
        token_request = _create_token_request(user_id, "notion", token_data, integration_data)
        result = await encrypt_token(user_id, token_request, supabase)
        
        return {
            "provider": "notion",
            "workspace_id": workspace_id,
            "integration_id": result.get("id") if isinstance(result, dict) else None
        }
    except DatabaseError as e:
        api_logger.error(f"Notion OAuth DB 오류: {str(e)}")
        raise
    except ValidationError as e:
        api_logger.error(f"Notion OAuth 검증 오류: {str(e)}")
        raise
    except Exception as e:
        api_logger.error(f"Notion OAuth 처리 실패: {str(e)}")
        raise DatabaseError(f"Notion OAuth 처리 실패: {str(e)}")
    
async def process_github_oauth(user_id: str, code: str, supabase: AsyncClient) -> dict:
    """GitHub OAuth 처리: 코드 교환, 토큰 저장"""
    try:
        # 1. GitHub 인증 서비스 초기화
        oauth_service = OAuthService()
        
        # 2. 코드를 토큰으로 교환
        token_data = await oauth_service.exchange_github_code(code)
        
        # 3. 필요한 토큰 데이터 추출
        access_token = token_data.get("access_token")
        
        # 4. 기존 통합 정보 확인 (업데이트를 위해)
        integration_data = await get_integration_by_id(user_id, "github", supabase)
        
        # 5. 통합 요청 객체 생성
        if integration_data:
            token_request = UserIntegrationRequest(
                id=integration_data["id"],
                user_id=user_id,
                provider="github",
                access_token=access_token,
                scopes=token_data.get("scope", "").split(",") if token_data.get("scope") else None
            )
        else:
            token_request = UserIntegrationRequest(
                user_id=user_id,
                provider="github",
                access_token=access_token,
                scopes=token_data.get("scope", "").split(",") if token_data.get("scope") else None
            )
        
        # 6. 토큰 암호화 및 저장
        result = await encrypt_token(user_id, token_request, supabase)
        
        # 7. 결과 반환
        return {
            "provider": "github",
            "integration_id": result.get("id") if isinstance(result, dict) else None
        }
    except DatabaseError as e:
        api_logger.error(f"GitHub OAuth DB 오류: {str(e)}")
        raise
    except ValidationError as e:
        api_logger.error(f"GitHub OAuth 검증 오류: {str(e)}")
        raise
    except Exception as e:
        api_logger.error(f"GitHub OAuth 처리 실패: {str(e)}")
        raise DatabaseError(f"GitHub OAuth 처리 실패: {str(e)}")


def _create_token_request(user_id: str, provider: str, token_data: dict, integration_data: dict = None) -> UserIntegrationRequest:
    """토큰 저장 요청 객체 생성 (내부 헬퍼 함수)"""
    base_args = {
        "user_id": user_id,
        "provider": provider,
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token"),
        "expires_in": token_data.get("expires_in"),
        "scopes": token_data.get("scope", "").split() if token_data.get("scope") else None
    }
    
    if integration_data:
        base_args["id"] = integration_data["id"]
        
    return UserIntegrationRequest(**base_args)