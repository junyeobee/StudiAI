from supabase import create_client

SUPABASE_URL = "https://gawybycxbfvfahjsxaaj.supabase.co"
SUPABASE_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imdhd3lieWN4YmZ2ZmFoanN4YWFqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUyODk2NTUsImV4cCI6MjA2MDg2NTY1NX0.zugL1rS5Tu4OumurqU5bm9bwL_7yMFcYF0QUEWHhCYQ"

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

# 페이지 아이디 가져오기
def get_ai_block_id_by_page_id(page_id):
    res = supabase.table("learning_pages").select("ai_block_id").eq("page_id", page_id).execute()
    data = res.data
    if data and "ai_block_id" in data[0]:
        return data[0]["ai_block_id"]
    return None

# 6. 상태가 'used'인 학습 데이터베이스 조회
def get_active_learning_database():
    res = supabase.table("learning_databases").select("id, db_id, title, parent_page_id").eq("status", "used").execute()
    data = res.data
    if data:
        # last_used_date 업데이트
        update_last_used_date(data[0]["id"])
        return data[0]
    return None

# 7. 학습 데이터베이스 상태 업데이트
def update_learning_database_status(db_id, status):
    res = supabase.table("learning_databases").update({"status": status, "updated_at": "now()"}).eq("db_id", db_id).execute()
    return res

# 8. 마지막 사용일 업데이트
def update_last_used_date(id):
    res = supabase.table("learning_databases").update({"last_used_date": "now()", "updated_at": "now()"}).eq("id", id).execute()
    return res

# 9. 사용 가능한 모든 학습 데이터베이스 조회 (ready 상태)
def get_available_learning_databases():
    res = supabase.table("learning_databases").select("id, db_id, title, parent_page_id").eq("status", "ready").execute()
    return res.data