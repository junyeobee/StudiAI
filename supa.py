from supabase import create_client

SUPABASE_URL = "https://gawybycxbfvfahjsxaaj.supabase.co"
SUPABASE_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imdhd3lieWN4YmZ2ZmFoanN4YWFqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDUyODk2NTUsImV4cCI6MjA2MDg2NTY1NX0.zugL1rS5Tu4OumurqU5bm9bwL_7yMFcYF0QUEWHhCYQ"
supabase = create_client(SUPABASE_URL, SUPABASE_API_KEY)

# 📥 1. 최상위 학습 DB 정보 저장
def insert_learning_database(db_id, title, parent_page_id):
    data = {
        "db_id": db_id,
        "title": title,
        "parent_page_id": parent_page_id
    }
    res = supabase.table("learning_databases").insert(data).execute()
    print(res)

# 📥 2. 일자별 학습 페이지 저장
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

# 📤 3. title 기준으로 Notion DB ID + Supabase DB UUID 조회
def get_learning_database_by_title(title):
    res = supabase.table("learning_databases").select("id, db_id").eq("title", title).execute()
    data = res.data
    if data:
        return data[0]["db_id"], data[0]["id"]
    return None, None

# 📤 4. 날짜 기준 학습 페이지 조회
def get_learning_page_by_date(date):
    res = supabase.table("learning_pages").select("*").eq("date", date).execute()
    print(res)

# 📤 5. page_id 기준 AI block ID 수정
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