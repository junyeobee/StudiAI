
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from notion_create import create_learning_pages
from supa import (
    get_active_learning_database, 
    get_available_learning_databases, 
    update_learning_database_status,
    insert_learning_database,
    get_learning_database_by_title,
    get_ai_block_id_by_page_id,
    get_learning_database_by_title, get_ai_block_id_by_page_id, 
    update_webhook_info, get_webhook_info, update_learning_database_status,
    list_all_learning_databases, get_learning_database_by_id

)
from notion_mdf import update_ai_summary_block
from notion_qry import list_databases_in_page

app = FastAPI()

# 📥 POST 요청 모델 정의
class PageRequest(BaseModel):
    db_title: str
    plans: list[dict]  # 여러 학습 계획 받아서 처리

class SummaryRequest(BaseModel):
    page_id: str
    summary: str

class WebhookUpdate(BaseModel):
    db_id: str
    webhook_id: str
    webhook_status: str = "active"


# 현재 활성화된 학습 DB 조회
@app.get("/active_database")
def get_active_db():
    active_db = get_active_learning_database()
    if not active_db:
        return {"status": "none", "message": "활성화된 데이터베이스가 없습니다."}
    return {"status": "active", "database": active_db}

# 사용 가능한 학습 DB 목록 조회
@app.get("/available_databases")
def get_available_dbs():
    dbs = get_available_learning_databases()
    return {"databases": dbs}

# 특정 Notion 페이지 내 DB 목록 조회
@app.get("/page_databases/{page_id}")
def get_page_dbs(page_id: str):
    databases = list_databases_in_page(page_id)
    if isinstance(databases, dict) and "error" in databases:
        return {"status": "error", "message": databases["error"]}
    return {"databases": databases}

# 학습 DB 활성화
@app.post("/activate_database")
def activate_db(db_id: str):
    active_db = get_active_learning_database()
    
    if active_db:
        update_learning_database_status(active_db['db_id'], 'ready')
    
    update_learning_database_status(db_id, 'used')
    return {"status": "activated", "db_id": db_id}

# 새 학습 DB 등록
@app.post("/register_database")
def register_db(req: dict):
    parent_page_id = req.get("parent_page_id")
    db_id = req.get("db_id")
    title = req.get("title")
    
    if not all([parent_page_id, db_id, title]):
        return {"status": "error", "message": "필수 파라미터가 누락되었습니다."}
    
    insert_learning_database(db_id, title, parent_page_id)
    return {"status": "registered", "db_id": db_id, "title": title}

# 학습 계획 페이지 생성 API
@app.post("/create_page")
def create_page(req: PageRequest):
    notion_db_id, learning_db_id = get_learning_database_by_title(req.db_title)
    print(f"요청 받음: {req}")
    print(notion_db_id)
    print(req.db_title)
    if not notion_db_id or not learning_db_id:
        return { "error": "해당 제목의 DB를 찾을 수 없습니다." }

    create_learning_pages(req.plans, notion_db_id, learning_db_id)
    return { "status": "created", "count": len(req.plans) }

# 요약 블록 내용 업데이트 API
@app.post("/fill_summary")
def fill_summary(req: SummaryRequest):
    ai_block_id = get_ai_block_id_by_page_id(req.page_id)
    if not ai_block_id:
        return { "error": "해당 페이지의 요약 블록 ID를 찾을 수 없습니다." }

    update_ai_summary_block(ai_block_id, req.summary)
    return { "status": "updated" }


@app.post("/update_webhook")
def update_webhook(req: WebhookUpdate):
    """웹훅 ID와 상태 업데이트"""
    result = update_webhook_info(req.db_id, req.webhook_id, req.webhook_status)
    
    if not result:
        raise HTTPException(status_code=404, detail="해당 ID의 데이터베이스를 찾을 수 없습니다.")
    
    return {
        "status": "updated",
        "db_id": req.db_id,
        "webhook_id": req.webhook_id
    }

@app.get("/get_webhook/{db_id}")
def get_webhook(db_id: str):
    """DB ID로 웹훅 정보 조회"""
    result = get_webhook_info(db_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="해당 ID의 데이터베이스를 찾을 수 없습니다.")
    
    return result

@app.post("/update_db_status")
def update_db_status(req: dict):
    """데이터베이스 상태 업데이트"""
    if "db_id" not in req or "status" not in req:
        raise HTTPException(status_code=400, detail="db_id와 status가 필요합니다.")
    
    if req["status"] not in ["ready", "used", "end"]:
        raise HTTPException(status_code=400, detail="status는 'ready', 'used', 'end' 중 하나여야 합니다.")
    
    result = update_learning_database_status(req["db_id"], req["status"])
    
    if not result:
        raise HTTPException(status_code=404, detail="해당 ID의 데이터베이스를 찾을 수 없습니다.")
    
    return {
        "status": "updated",
        "db_id": result["db_id"],
        "title": result["title"],
        "new_status": result["status"]
    }

@app.get("/list_all_dbs")
def list_all_dbs(status: str = None):
    """모든 학습 DB 목록 조회"""
    return list_all_learning_databases(status)

@app.get("/get_db/{db_id}")
def get_db(db_id: str):
    """특정 DB 정보 조회"""
    db = get_learning_database_by_id(db_id)
    if not db:
        raise HTTPException(status_code=404, detail="해당 ID의 데이터베이스를 찾을 수 없습니다.")
    return db

@app.get("/list_db_in_page")
def list_db_in_page(parent_page_id: str):
    """페이지 내 DB 목록 조회"""
    return list_databases_in_page(parent_page_id)