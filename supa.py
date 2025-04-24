from supabase import create_client
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

SUPABASE_URL = "https://gawybycxbfvfahjsxaaj.supabase.co"
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_API_KEY)

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