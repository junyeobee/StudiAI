from supabase._async.client import AsyncClient
from datetime import datetime
from app.core.config import settings
from app.utils.logger import api_logger, webhook_logger
import httpx
from typing import Optional

async def insert_learning_database(db_id: str, title: str, parent_page_id: str, supabase: AsyncClient, user_id: str) -> bool:
    """새로운 학습 데이터베이스 등록"""
    try:
        data = {
            "db_id": db_id,
            "title": title,
            "parent_page_id": parent_page_id,
            "status": "ready",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "user_id": user_id
        }
        res = await supabase.table("learning_databases").insert(data).execute()
        return bool(res.data)
    except Exception as e:
        api_logger.error(f"데이터베이스 등록 실패: {str(e)}")
        return False


async def get_learning_database_by_title(title: str, supabase: AsyncClient, user_id: str) -> tuple:
    """제목으로 학습 데이터베이스 정보 조회"""
    try:
        res = await supabase.table("learning_databases").select("id, db_id").eq("title", title).eq("user_id", user_id).execute()
        data = res.data
        if data:
            return data[0]["db_id"], data[0]["id"]
        return None, None
    except Exception as e:
        api_logger.error(f"데이터베이스 조회 실패: {str(e)}")
        return None, None

async def get_active_learning_database(supabase: AsyncClient, user_id: str) -> dict:
    """현재 활성화된 학습 데이터베이스 조회"""
    try:
        res = await supabase.table("learning_databases").select("*").eq("status", "used").eq("user_id", user_id).execute()
        data = res.data
        if data:
            await update_last_used_date(data[0]["id"], supabase, user_id)
            return data[0]
        return None
    except Exception as e:
        api_logger.error(f"활성 데이터베이스 조회 실패: {str(e)}")
        return None

async def update_learning_database_status(db_id: Optional[str], status: str, supabase: AsyncClient, user_id: str) -> dict:
    """학습 데이터베이스 상태 업데이트"""
    try:
        # 기존 used 상태인 레코드 여부
        resp = await supabase.table("learning_databases") \
            .select("id") \
            .eq("status", "used") \
            .eq("user_id", user_id) \
            .execute()
        print(resp)
        old_id = resp.data[0]["id"] if resp.data else None

        # 비활성화 요청 시, 활성화된 DB가 없으면 바로 None 반환
        if status == "ready" and old_id is None:
            return None

        # RPC
        new_db_id_param = db_id if status == "used" else None
        res = await supabase.rpc("activate_db_transaction", {
            "old_rec_id": old_id,
            "new_db_id":  new_db_id_param
        }).execute()
        
        data = res.data
        if not data:
            return None

        if isinstance(data, list):
            return data[0]
        if isinstance(data, dict):
            return data

        return None
        
    except Exception as e:
        api_logger.error(f"DB 상태 업데이트 실패(db_id={db_id}, status={status}): {e}")
        return None

async def update_last_used_date(id: int, supabase: AsyncClient, user_id: str) -> bool:
    """마지막 사용일 업데이트"""
    try:
        res = await supabase.table("learning_databases").update({
            "last_used_date": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "user_id": user_id
        }).eq("id", id).execute()
        return bool(res.data)
    except Exception as e:
        api_logger.error(f"마지막 사용일 업데이트 실패: {str(e)}")
        return False

async def get_available_learning_databases(supabase: AsyncClient, user_id: str) -> list:
    """사용 가능한 학습 데이터베이스 목록 조회"""
    try:
        res = await supabase.table("learning_databases").select("*").eq("status", "ready").eq("user_id", user_id).execute()
        return res.data if res and hasattr(res, 'data') else []
    except Exception as e:
        api_logger.error(f"사용 가능한 데이터베이스 조회 실패: {str(e)}")
        return []

async def list_all_learning_databases(supabase: AsyncClient, user_id: str, status: str = None) -> list:
    """모든 학습 데이터베이스 목록 조회"""
    try:
        query = supabase.table("learning_databases").select("*").eq("user_id", user_id)
        if status:
            query = query.eq("status", status)
        res = await query.order("updated_at", desc=True).execute()
        return res.data if res and hasattr(res, 'data') else []
    except Exception as e:
        api_logger.error(f"데이터베이스 목록 조회 실패: {str(e)}")
        return []

async def get_db_info_by_id(db_id: str, supabase: AsyncClient, user_id: str) -> dict:
    """데이터베이스 ID로 정보 조회"""
    try:
        res = await supabase.table("learning_databases").select("*").eq("db_id", db_id).eq("user_id", user_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        api_logger.error(f"데이터베이스 정보 조회 실패: {str(e)}")
        return None

# 현재 사용중인 Notion DB ID 조회
async def get_used_notion_db_id(supabase: AsyncClient, user_id: str) -> str | None:
    """현재 사용중인 Notion DB ID 조회"""
    res = await supabase.table("learning_databases") \
        .select("db_id") \
        .eq("status", "used") \
        .eq("user_id", user_id) \
        .single() \
        .execute()
    return res.data["db_id"] if res.data else None

async def update_webhook_info(db_id: str, webhook_id: str, supabase: AsyncClient, status: str = "active") -> dict:
    """웹훅 정보 업데이트"""
    try:
        update_data = {
            "webhook_id": webhook_id,
            "webhook_status": status,
            "updated_at": datetime.now().isoformat()
        }
        
        if status == "error":
            update_data["webhook_error"] = "웹훅 생성/업데이트 중 오류 발생"
        
        res = await supabase.table("learning_databases").update(update_data).eq("db_id", db_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        api_logger.error(f"웹훅 정보 업데이트 실패: {str(e)}")
        return None

async def get_webhook_info(db_id: str, supabase: AsyncClient) -> dict:
    """웹훅 정보 조회"""
    try:
        res = await supabase.table("learning_databases").select("webhook_id, webhook_status").eq("db_id", db_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        api_logger.error(f"웹훅 정보 조회 실패: {str(e)}")
        return None

async def get_webhook_info_by_db_id(db_id: str, supabase: AsyncClient) -> dict:
    """DB ID로 웹훅 정보를 조회"""
    try:
        res = await supabase.table("learning_databases").select("webhook_id, webhook_status").eq("db_id", db_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        api_logger.error(f"웹훅 정보 조회 실패: {str(e)}")
        return None

async def log_webhook_operation(db_id: str, operation_type: str, status: str, supabase: AsyncClient, error_message: str = None, webhook_id: str = None) -> bool:
    """웹훅 작업 로그 기록"""
    try:
        data = {
            "db_id": db_id,
            "operation_type": operation_type,
            "status": status,
            "webhook_id": webhook_id,
            "error_message": error_message,
            "updated_at": datetime.now().isoformat()
        }
        res = await supabase.table("webhook_operations").insert(data).execute()
        return bool(res.data)
    except Exception as e:
        api_logger.error(f"웹훅 작업 로그 기록 실패: {str(e)}")
        return False

async def insert_learning_page(date: str, title: str, page_id: str, ai_block_id: str, learning_db_id: str, supabase: AsyncClient) -> bool:
    """학습 페이지 저장"""
    try:
        data = {
            "date": date,
            "title": title,
            "page_id": page_id,
            "ai_block_id": ai_block_id,
            "learning_db_id": learning_db_id
        }
        res = await supabase.table("learning_pages").insert(data).execute()
        return bool(res.data)
    except Exception as e:
        api_logger.error(f"학습 페이지 저장 실패: {str(e)}")
        return False

async def get_learning_page_by_date(date: str, supabase: AsyncClient) -> dict:
    """날짜별 학습 페이지 조회"""
    try:
        res = await supabase.table("learning_pages").select("*").eq("date", date).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        api_logger.error(f"학습 페이지 조회 실패: {str(e)}")
        return None

async def update_ai_block_id(page_id: str, new_ai_block_id: str, supabase: AsyncClient) -> bool:
    """AI 블록 ID 업데이트"""
    try:
        res = await supabase.table("learning_pages").update({"ai_block_id": new_ai_block_id}).eq("page_id", page_id).execute()
        return bool(res.data)
    except Exception as e:
        api_logger.error(f"AI 블록 ID 업데이트 실패: {str(e)}")
        return False

async def get_ai_block_id_by_page_id(page_id: str, supabase: AsyncClient) -> str:
    """페이지 ID로 AI 블록 ID 조회"""
    try:
        res = await supabase.table("learning_pages").select("ai_block_id").eq("page_id", page_id).execute()
        data = res.data
        if data and "ai_block_id" in data[0]:
            return data[0]["ai_block_id"]
        return None
    except Exception as e:
        api_logger.error(f"AI 블록 ID 조회 실패: {str(e)}")
        return None

async def get_failed_webhook_operations(supabase: AsyncClient, limit: int = 10) -> list:
    """실패한 웹훅 작업 조회"""
    try:
        res = await supabase.table("webhook_operations")\
            .select("*")\
            .eq("status", "failed")\
            .lte("retry_count", 3)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        return res.data if res and hasattr(res, 'data') else []
    except Exception as e:
        api_logger.error(f"실패한 웹훅 작업 조회 실패: {str(e)}")
        return []

async def update_webhook_operation_status(operation_id: int, status: str, supabase: AsyncClient, error_message: str = None) -> bool:
    """웹훅 작업 상태 업데이트"""
    try:
        update_data = {
            "status": status,
            "updated_at": datetime.now().isoformat()
        }
        
        if error_message:
            update_data["error_message"] = error_message
        
        if status == "retry":
            res = await supabase.table("webhook_operations")\
                .update({
                    **update_data,
                    "retry_count": supabase.raw("retry_count + 1")
                })\
                .eq("id", operation_id)\
                .execute()
        else:
            res = await supabase.table("webhook_operations")\
                .update(update_data)\
                .eq("id", operation_id)\
                .execute()
        
        return bool(res.data)
    except Exception as e:
        api_logger.error(f"웹훅 작업 상태 업데이트 실패: {str(e)}")
        return False

async def verify_all_webhooks(supabase: AsyncClient) -> dict:
    """모든 활성 웹훅의 상태를 검증"""
    try:
        res = await supabase.table("learning_databases")\
            .select("*")\
            .eq("webhook_status", "active")\
            .execute()
        
        active_dbs = res.data if res and hasattr(res, 'data') else []
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

async def retry_failed_webhook_operations(supabase: AsyncClient) -> dict:
    """실패한 웹훅 작업을 재시도"""
    try:
        res = await supabase.table("webhook_operations")\
            .select("*")\
            .eq("status", "failed")\
            .lte("retry_count", 3)\
            .order("created_at", desc=True)\
            .execute()
        
        failed_operations = res.data if res and hasattr(res, 'data') else []
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
                    if operation_type == "create":
                        webhook_url = settings.WEBHOOK_CREATE_URL
                        response = await client.post(
                            webhook_url,
                            json={"db_id": db_id},
                            timeout=30.0
                        )
                    elif operation_type == "delete":
                        webhook_url = settings.WEBHOOK_DELETE_URL
                        response = await client.post(
                            webhook_url,
                            json={"db_id": db_id},
                            timeout=30.0
                        )
                    else:
                        raise ValueError(f"Unknown operation type: {operation_type}")
                    
                    if response.status_code == 200:
                        await update_webhook_operation_status(
                            operation_id,
                            "success",
                            None
                        )
                        retried += 1
                        webhook_logger.info(f"Successfully retried operation {operation_id} for DB: {db_id}")
                    else:
                        await update_webhook_operation_status(
                            operation_id,
                            "failed",
                            f"HTTP {response.status_code}: {response.text}"
                        )
                        failed += 1
                        errors.append({
                            "operation_id": operation_id,
                            "db_id": db_id,
                            "error": f"HTTP {response.status_code}: {response.text}"
                        })
                        webhook_logger.error(f"Failed to retry operation {operation_id} for DB: {db_id}")
                        
                except Exception as e:
                    await update_webhook_operation_status(
                        operation_id,
                        "failed",
                        str(e)
                    )
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

async def get_databases_in_page(page_id: str, supabase: AsyncClient) -> list:
    """특정 Notion 페이지 내의 모든 데이터베이스를 조회"""
    try:
        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        headers = {
            "Authorization": f"Bearer {settings.NOTION_API_KEY}",
            "Notion-Version": settings.NOTION_API_VERSION,
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=30.0)
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

async def activate_database(db_id: str, supabase: AsyncClient) -> bool:
    """데이터베이스를 활성화"""
    try:
        active_db = await get_active_learning_database(supabase)
        if active_db:
            await update_learning_database_status(active_db['db_id'], 'ready')
        
        await update_learning_database_status(db_id, 'used')
        return True
    except Exception as e:
        api_logger.error(f"Error activating database: {str(e)}")
        return False

async def deactivate_database(db_id: str, supabase: AsyncClient, end_status: bool = False) -> bool:
    """데이터베이스를 비활성화"""
    try:
        new_status = 'end' if end_status else 'ready'
        await update_learning_database_status(db_id, new_status)
        return True
    except Exception as e:
        api_logger.error(f"Error deactivating database: {str(e)}")
        return False

async def update_learning_database(db_id: str, update_data: dict, supabase: AsyncClient) -> dict:
    """학습 DB 정보 업데이트"""
    try:
        update_data["updated_at"] = datetime.now().isoformat()
        res = await supabase.table("learning_databases").update(update_data).eq("db_id", db_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        api_logger.error(f"DB 업데이트 실패: {str(e)}")
        return None
    
async def delete_learning_page(page_id: str, supabase: AsyncClient) -> None:
    """학습 페이지 삭제"""
    try : 
        await supabase.table("learning_pages").delete().eq("page_id", page_id).execute()
    except Exception as e:
        api_logger.error(f"학습 페이지 메타 삭제 실패: {str(e)}")
        return None

async def auth_user(user_id:str, auth_token:str, supabase: AsyncClient) -> dict:
    """유저 인증"""
    try:
        res = await supabase.auth.admin.getUserById(user_id)
        return res.data
    except Exception as e:
        api_logger.error(f"유저 인증 실패: {str(e)}")
        return None
