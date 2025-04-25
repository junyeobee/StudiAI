from supabase import create_client
from dotenv import load_dotenv
import os
from datetime import datetime
from app.core.config import settings
from app.utils.logger import api_logger, webhook_logger
import httpx

load_dotenv()

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

# 최상위 학습 DB 정보 저장
def insert_learning_database(db_id, title, parent_page_id):
    data = {
        "db_id": db_id,
        "title": title,
        "parent_page_id": parent_page_id
    }
    res = supabase.table("learning_databases").insert(data).execute()
    print(res)

# 일자별 학습 페이지 저장
def insert_learning_page(date, title, page_id, ai_block_id, learning_db_id):
    data = {
        "date": date,
        "title": title,
        "page_id": page_id,
        "ai_block_id": ai_block_id,
        "learning_db_id": learning_db_id
    }
    res = supabase.table("learning_pages").insert(data).execute()
    print(res)

# title 기준으로 Notion DB ID + Supabase DB UUID 조회
def get_learning_database_by_title(title):
    res = supabase.table("learning_databases").select("id, db_id").eq("title", title).execute()
    data = res.data
    if data:
        return data[0]["db_id"], data[0]["id"]
    return None, None

# 날짜 기준 학습 페이지 조회
def get_learning_page_by_date(date):
    res = supabase.table("learning_pages").select("*").eq("date", date).execute()
    print(res)

# page_id 기준 AI block ID 수정
def update_ai_block_id(page_id, new_ai_block_id):
    res = supabase.table("learning_pages").update({"ai_block_id": new_ai_block_id}).eq("page_id", page_id).execute()
    print(res)

# 페이지 ID 가져오기
def get_ai_block_id_by_page_id(page_id):
    res = supabase.table("learning_pages").select("ai_block_id").eq("page_id", page_id).execute()
    data = res.data
    if data and "ai_block_id" in data[0]:
        return data[0]["ai_block_id"]
    return None

# 상태가 'used'인 학습 DB 조회
def get_active_learning_database():
    res = supabase.table("learning_databases").select("id, db_id, title, parent_page_id").eq("status", "used").execute()
    data = res.data
    if data:
        # last_used_date 업데이트
        update_last_used_date(data[0]["id"])
        return data[0]
    return None

# 학습 DB 상태 업데이트
def update_learning_database_status(db_id, status):
    res = supabase.table("learning_databases").update({"status": status, "updated_at": "now()"}).eq("db_id", db_id).execute()
    return res

# 마지막 사용일 업데이트
def update_last_used_date(id):
    res = supabase.table("learning_databases").update({"last_used_date": "now()", "updated_at": "now()"}).eq("id", id).execute()
    return res

# 사용 가능 학습 DB 조회 (ready 상태)
def get_available_learning_databases():
    res = supabase.table("learning_databases").select("id, db_id, title, parent_page_id").eq("status", "ready").execute()
    return res.data

# DB 웹훅 정보 업데이트
def update_webhook_info(db_id, webhook_id, status="active"):
    res = supabase.table("learning_databases").update({
        "webhook_id": webhook_id,
        "webhook_status": status,
        "updated_at": datetime.now().isoformat()
    }).eq("db_id", db_id).execute()
    
    if res.data and len(res.data) > 0:
        return res.data[0]
    return None

# DB 웹훅 정보 조회
def get_webhook_info(db_id):
    res = supabase.table("learning_databases").select("webhook_id, webhook_status").eq("db_id", db_id).execute()
    if res.data and len(res.data) > 0:
        return res.data[0]
    return None

# DB 상태 업데이트
def update_learning_database_status(db_id, new_status):
    """
    학습 데이터베이스 상태 업데이트
    
    Args:
        db_id: Notion 데이터베이스 ID
        new_status: 새 상태 (ready, used, end)
    """
    # 'used'로 변경하는 경우, 기존 used DB를 ready로 변경
    if new_status == "used":
        supabase.table("learning_databases").update({
            "status": "ready",
            "updated_at": datetime.now().isoformat()
        }).eq("status", "used").execute()
    
    # 지정된 DB 상태 변경
    res = supabase.table("learning_databases").update({
        "status": new_status,
        "last_used_date": datetime.today().strftime("%Y-%m-%d"),
        "updated_at": datetime.now().isoformat()
    }).eq("db_id", db_id).execute()
    
    if res.data and len(res.data) > 0:
        return res.data[0]
    return None

# 모든 학습 DB 조회
def list_all_learning_databases(status=None):
    """
    모든 학습 DB 조회 (상태 필터 옵션)
    
    Args:
        status: 필터링할 상태 (ready, used, end) - None이면 모든 상태 반환
    """
    query = supabase.table("learning_databases").select("id, db_id, title, status, last_used_date, created_at, updated_at, webhook_id, webhook_status")
    
    if status:
        query = query.eq("status", status)
    
    res = query.order("updated_at", desc=True).execute()
    return res.data

# DB ID로 학습 DB 조회
def get_learning_database_by_id(db_id):
    """DB ID로 학습 DB 조회"""
    res = supabase.table("learning_databases").select("*").eq("db_id", db_id).execute()
    if res.data and len(res.data) > 0:
        return res.data[0]
    return None

def get_db_info_by_id(db_id: str) -> dict:
    """
    DB ID로 데이터베이스 정보를 조회합니다.
    
    Args:
        db_id (str): 조회할 데이터베이스 ID
        
    Returns:
        dict: 데이터베이스 정보 (없으면 None)
    """
    try:
        # learning_databases 테이블에서 DB 정보 조회
        response = supabase.table("learning_databases")\
            .select("*")\
            .eq("db_id", db_id)\
            .execute()
        
        if not response.data:
            api_logger.warning(f"Database not found with ID: {db_id}")
            return None
            
        db_info = response.data[0]
        api_logger.info(f"Retrieved database info for ID: {db_id}")
        
        return {
            "db_id": db_info.get("db_id"),
            "title": db_info.get("title"),
            "parent_page_id": db_info.get("parent_page_id"),
            "status": db_info.get("status"),
            "webhook_id": db_info.get("webhook_id"),
            "webhook_status": db_info.get("webhook_status"),
            "last_used_date": db_info.get("last_used_date"),
            "created_at": db_info.get("created_at"),
            "updated_at": db_info.get("updated_at")
        }
        
    except Exception as e:
        api_logger.error(f"Error retrieving database info: {str(e)}")
        return None

# DB ID로 웹훅 정보 조회
def get_webhook_info_by_db_id(db_id):
    """DB ID로 웹훅 정보를 조회합니다."""
    try:
        res = supabase.table("learning_databases").select("webhook_id, webhook_status").eq("db_id", db_id).execute()
        data = res.data
        if data:
            return data[0]
        return None
    except Exception as e:
        print(f"웹훅 정보 조회 오류: {str(e)}")
        return None

# 웹훅 정보 업데이트
def update_webhook_info(db_id, webhook_id, webhook_status):
    """웹훅 정보를 업데이트합니다."""
    try:
        update_data = {
            "webhook_id": webhook_id,
            "webhook_status": webhook_status,
            "updated_at": "now()",
            "last_webhook_check": "now()"
        }
        
        if webhook_status == "error":
            update_data["webhook_error"] = "웹훅 생성/업데이트 중 오류 발생"
        
        res = supabase.table("learning_databases").update(update_data).eq("db_id", db_id).execute()
        return bool(res.data)
    except Exception as e:
        print(f"웹훅 정보 업데이트 오류: {str(e)}")
        return False

# 웹훅 작업 로그 기록
def log_webhook_operation(db_id, operation_type, status, error_message=None, webhook_id=None):
    """웹훅 작업 로그를 기록합니다."""
    try:
        data = {
            "db_id": db_id,
            "operation_type": operation_type,
            "status": status,
            "webhook_id": webhook_id,
            "error_message": error_message,
            "updated_at": "now()"
        }
        
        res = supabase.table("webhook_operations").insert(data).execute()
        return bool(res.data)
    except Exception as e:
        print(f"웹훅 작업 로그 기록 오류: {str(e)}")
        # 로깅 실패 시에도 작업은 계속 진행
        return False

# 현재 사용 중인 학습 DB 정보 조회
def get_current_learning_database_info():
    """현재 'used' 상태인 학습 데이터베이스 정보를 반환합니다."""
    try:
        res = supabase.table("learning_databases").select("*").eq("status", "used").execute()
        data = res.data
        if data:
            return data[0]
        return None
    except Exception as e:
        print(f"현재 DB 조회 오류: {str(e)}")
        return None

# 모든 학습 DB 목록 조회
def list_all_learning_databases():
    """모든 학습 데이터베이스 목록을 반환합니다."""
    try:
        res = supabase.table("learning_databases").select("*").order("updated_at", desc=True).execute()
        return res.data
    except Exception as e:
        print(f"DB 목록 조회 오류: {str(e)}")
        return []

# 실패한 웹훅 작업 조회
def get_failed_webhook_operations(limit=10):
    """실패한 웹훅 작업을 조회합니다."""
    try:
        res = supabase.table("webhook_operations")\
            .select("*")\
            .eq("status", "failed")\
            .lte("retry_count", 3)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        return res.data
    except Exception as e:
        print(f"실패한 작업 조회 오류: {str(e)}")
        return []

# 웹훅 작업 상태 업데이트
def update_webhook_operation_status(operation_id, status, error_message=None):
    """웹훅 작업 상태를 업데이트합니다."""
    try:
        update_data = {
            "status": status,
            "updated_at": "now()"
        }
        
        if error_message:
            update_data["error_message"] = error_message
        
        if status == "retry":
            # 재시도 카운트 증가 (raw SQL 사용)
            res = supabase.table("webhook_operations")\
                .update({
                    **update_data,
                    "retry_count": supabase.raw("retry_count + 1")
                })\
                .eq("id", operation_id)\
                .execute()
        else:
            res = supabase.table("webhook_operations")\
                .update(update_data)\
                .eq("id", operation_id)\
                .execute()
        
        return bool(res.data)
    except Exception as e:
        print(f"작업 상태 업데이트 오류: {str(e)}")
        return False

# 웹훅 상태 검증 및 복구 (비동기 함수)
async def verify_all_webhooks() -> dict:
    """
    모든 활성 웹훅의 상태를 검증합니다.
    
    Returns:
        dict: 검증 결과
            - total: 전체 웹훅 수
            - verified: 검증 성공 수
            - failed: 검증 실패 수
            - errors: 에러 목록
    """
    try:
        # 활성 웹훅이 있는 DB 조회
        response = supabase.table("learning_databases")\
            .select("*")\
            .eq("webhook_status", "active")\
            .execute()
        
        active_dbs = response.data
        total = len(active_dbs)
        verified = 0
        failed = 0
        errors = []
        
        webhook_logger.info(f"Starting verification of {total} active webhooks")
        
        async with httpx.AsyncClient() as client:
            for db in active_dbs:
                db_id = db.get("db_id")
                webhook_id = db.get("webhook_id")
                
                try:
                    # 웹훅 상태 확인을 위한 ping 요청
                    # 실제 구현에서는 Notion API를 통해 웹훅 상태 확인
                    # 여기서는 예시로 간단한 HTTP 요청을 보냄
                    ping_url = f"https://api.notion.com/v1/webhooks/{webhook_id}"
                    response = await client.get(
                        ping_url,
                        headers={
                            "Authorization": f"Bearer {settings.NOTION_API_KEY}",
                            "Notion-Version": settings.NOTION_API_VERSION
                        },
                        timeout=10.0
                    )
                    
                    if response.status_code == 200:
                        verified += 1
                        webhook_logger.info(f"Webhook verified successfully for DB: {db_id}")
                    else:
                        failed += 1
                        errors.append({
                            "db_id": db_id,
                            "error": f"HTTP {response.status_code}: {response.text}"
                        })
                        webhook_logger.error(f"Webhook verification failed for DB: {db_id}")
                        
                except Exception as e:
                    failed += 1
                    errors.append({
                        "db_id": db_id,
                        "error": str(e)
                    })
                    webhook_logger.error(f"Error verifying webhook for DB {db_id}: {str(e)}")
        
        result = {
            "total": total,
            "verified": verified,
            "failed": failed,
            "errors": errors
        }
        
        webhook_logger.info(f"Webhook verification completed: {result}")
        return result
        
    except Exception as e:
        webhook_logger.error(f"Error in verify_all_webhooks: {str(e)}")
        return {
            "total": 0,
            "verified": 0,
            "failed": 0,
            "errors": [str(e)]
        }

# 실패한 웹훅 작업 재시도 (비동기 함수)
async def retry_failed_webhook_operations() -> dict:
    """
    실패한 웹훅 작업을 재시도합니다.
    
    Returns:
        dict: 재시도 결과
            - total: 전체 실패 작업 수
            - retried: 재시도 성공 수
            - failed: 재시도 실패 수
            - errors: 에러 목록
    """
    try:
        # 실패한 웹훅 작업 조회 (최대 3번까지 재시도)
        response = supabase.table("webhook_operations")\
            .select("*")\
            .eq("status", "failed")\
            .lte("retry_count", 3)\
            .order("created_at", desc=True)\
            .execute()
        
        failed_operations = response.data
        total = len(failed_operations)
        retried = 0
        failed = 0
        errors = []
        
        webhook_logger.info(f"Starting retry of {total} failed webhook operations")
        
        async with httpx.AsyncClient() as client:
            for operation in failed_operations:
                operation_id = operation.get("id")
                db_id = operation.get("db_id")
                operation_type = operation.get("operation_type")
                
                try:
                    # 작업 유형에 따른 재시도 로직
                    if operation_type == "create":
                        # 웹훅 생성 재시도
                        webhook_url = settings.WEBHOOK_CREATE_URL
                        response = await client.post(
                            webhook_url,
                            json={"db_id": db_id},
                            timeout=30.0
                        )
                    elif operation_type == "delete":
                        # 웹훅 삭제 재시도
                        webhook_url = settings.WEBHOOK_DELETE_URL
                        response = await client.post(
                            webhook_url,
                            json={"db_id": db_id},
                            timeout=30.0
                        )
                    else:
                        raise ValueError(f"Unknown operation type: {operation_type}")
                    
                    if response.status_code == 200:
                        # 재시도 성공 시 상태 업데이트
                        supabase.table("webhook_operations")\
                            .update({
                                "status": "success",
                                "retry_count": operation.get("retry_count", 0) + 1,
                                "updated_at": datetime.now().isoformat()
                            })\
                            .eq("id", operation_id)\
                            .execute()
                        
                        retried += 1
                        webhook_logger.info(f"Successfully retried operation {operation_id} for DB: {db_id}")
                    else:
                        # 재시도 실패 시 상태 업데이트
                        supabase.table("webhook_operations")\
                            .update({
                                "retry_count": operation.get("retry_count", 0) + 1,
                                "error_message": f"HTTP {response.status_code}: {response.text}",
                                "updated_at": datetime.now().isoformat()
                            })\
                            .eq("id", operation_id)\
                            .execute()
                        
                        failed += 1
                        errors.append({
                            "operation_id": operation_id,
                            "db_id": db_id,
                            "error": f"HTTP {response.status_code}: {response.text}"
                        })
                        webhook_logger.error(f"Failed to retry operation {operation_id} for DB: {db_id}")
                        
                except Exception as e:
                    # 예외 발생 시 상태 업데이트
                    supabase.table("webhook_operations")\
                        .update({
                            "retry_count": operation.get("retry_count", 0) + 1,
                            "error_message": str(e),
                            "updated_at": datetime.now().isoformat()
                        })\
                        .eq("id", operation_id)\
                        .execute()
                    
                    failed += 1
                    errors.append({
                        "operation_id": operation_id,
                        "db_id": db_id,
                        "error": str(e)
                    })
                    webhook_logger.error(f"Error retrying operation {operation_id} for DB {db_id}: {str(e)}")
        
        result = {
            "total": total,
            "retried": retried,
            "failed": failed,
            "errors": errors
        }
        
        webhook_logger.info(f"Webhook operation retry completed: {result}")
        return result
        
    except Exception as e:
        webhook_logger.error(f"Error in retry_failed_webhook_operations: {str(e)}")
        return {
            "total": 0,
            "retried": 0,
            "failed": 0,
            "errors": [str(e)]
        }

def get_databases_in_page(page_id: str) -> list:
    """
    특정 Notion 페이지 내의 모든 데이터베이스를 조회합니다.
    
    Args:
        page_id (str): 조회할 Notion 페이지 ID
        
    Returns:
        list: 페이지 내 데이터베이스 목록
    """
    try:
        # Notion API를 통해 페이지 내 데이터베이스 조회
        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        headers = {
            "Authorization": f"Bearer {settings.NOTION_API_KEY}",
            "Notion-Version": settings.NOTION_API_VERSION,
            "Content-Type": "application/json"
        }
        
        response = httpx.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        
        blocks = response.json().get("results", [])
        databases = []
        
        for block in blocks:
            if block.get("type") == "child_database":
                database = {
                    "id": block.get("id"),
                    "title": block.get("child_database", {}).get("title"),
                    "created_time": block.get("created_time"),
                    "last_edited_time": block.get("last_edited_time")
                }
                databases.append(database)
        
        api_logger.info(f"Found {len(databases)} databases in page {page_id}")
        return databases
        
    except httpx.HTTPError as e:
        api_logger.error(f"HTTP error while fetching databases: {str(e)}")
        return []
    except Exception as e:
        api_logger.error(f"Error fetching databases: {str(e)}")
        return []

def activate_database(db_id: str) -> bool:
    """
    데이터베이스를 활성화합니다.
    
    Args:
        db_id (str): 활성화할 데이터베이스 ID
        
    Returns:
        bool: 성공 여부
    """
    try:
        # 현재 활성화된 DB를 ready 상태로 변경
        active_db = get_active_learning_database()
        if active_db:
            update_learning_database_status(active_db['db_id'], 'ready')
        
        # 새 DB를 used 상태로 변경
        update_learning_database_status(db_id, 'used')
        return True
    except Exception as e:
        api_logger.error(f"Error activating database: {str(e)}")
        return False

def deactivate_database(db_id: str, end_status: bool = False) -> bool:
    """
    데이터베이스를 비활성화합니다.
    
    Args:
        db_id (str): 비활성화할 데이터베이스 ID
        end_status (bool): 완료 상태로 변경할지 여부
        
    Returns:
        bool: 성공 여부
    """
    try:
        new_status = 'end' if end_status else 'ready'
        update_learning_database_status(db_id, new_status)
        return True
    except Exception as e:
        api_logger.error(f"Error deactivating database: {str(e)}")
        return False