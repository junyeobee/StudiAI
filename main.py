
from fastapi import FastAPI
from pydantic import BaseModel
from notion_create import create_learning_pages
from supa import get_learning_database_by_title
from supa import get_ai_block_id_by_page_id
from notion_mdf import update_ai_summary_block

app = FastAPI()

# 📥 POST 요청 모델 정의
class PageRequest(BaseModel):
    db_title: str
    plans: list[dict]  # 여러 학습 계획 받아서 처리

class SummaryRequest(BaseModel):
    page_id: str
    summary: str

# ✅ 학습 계획 페이지 생성 API
@app.post("/create_page")
def create_page(req: PageRequest):
    notion_db_id, learning_db_id = get_learning_database_by_title(req.db_title)
    if not notion_db_id or not learning_db_id:
        return { "error": "해당 제목의 DB를 찾을 수 없습니다." }

    create_learning_pages(req.plans, notion_db_id, learning_db_id)
    return { "status": "created", "count": len(req.plans) }

# ✅ 요약 블록 내용 업데이트 API
@app.post("/fill_summary")
def fill_summary(req: SummaryRequest):
    ai_block_id = get_ai_block_id_by_page_id(req.page_id)
    if not ai_block_id:
        return { "error": "해당 페이지의 요약 블록 ID를 찾을 수 없습니다." }

    update_ai_summary_block(ai_block_id, req.summary)
    return { "status": "updated" }
