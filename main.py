"""
메인 애플리케이션
"""
from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import httpx
import json
import os
from datetime import datetime
import logging
from app.core.config import settings
from app.utils.logger import api_logger, webhook_logger
from app.utils.exceptions import handle_exception
from app.services.notion_service import NotionService
from app.services.webhook_service import WebhookService
from app.utils.webhook import log_webhook_operation
from supa import (
    insert_learning_database,
    insert_learning_page,
    get_learning_database_by_title,
    get_learning_page_by_date,
    update_ai_block_id,
    get_ai_block_id_by_page_id,
    get_active_learning_database,
    update_learning_database_status,
    update_last_used_date,
    get_available_learning_databases,
    update_webhook_info,
    get_webhook_info,
    get_db_info_by_id,
    verify_all_webhooks,
    retry_failed_webhook_operations,
    get_databases_in_page,
    get_webhook_info_by_db_id,
    get_current_learning_database_info,
    list_all_learning_databases,
    get_learning_database_by_id,
    get_failed_webhook_operations,
    update_webhook_operation_status,
    activate_database,
    deactivate_database
)
from notion_create import create_learning_pages
from notion_mdf import update_ai_summary_block
from notion_qry import list_databases_in_page
from app.api.v1.api import api_router
from app.utils.logger import setup_logging

# 로깅 설정
setup_logging()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록
app.include_router(api_router, prefix=settings.API_V1_STR)

# POST 요청 모델 정의
class PageRequest(BaseModel):
    db_title: str
    plans: list[dict]  # 여러 학습 계획 받아서 처리

# 요약 요청시 구조
class SummaryRequest(BaseModel):
    page_id: str
    summary: str

# 웹훅 시 필요한 정보(특정 db에 대해서 웹훅으로 db감시 여부 지정)
class WebhookInfo(BaseModel):
    db_id: str
    webhook_id: Optional[str] = None
    webhook_status: str = "inactive"

# make.com 시나리오에서 감시중인 db를 webhook opeartion 테이블로 관리하기 위한 구조
class WebhookOperation(BaseModel):
    db_id: str
    operation_type: str
    webhook_id: Optional[str] = None
    status: str = "pending"
    error_message: Optional[str] = None

# supabase에서 관리하는 노션db
class DatabaseInfo(BaseModel):
    db_id: str
    title: str
    parent_page_id: str
    status: str
    webhook_id: Optional[str] = None
    webhook_status: Optional[str] = None
    last_used_date: Optional[str] = None


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
def update_webhook(req: WebhookInfo):
    """웹훅 ID와 상태 업데이트"""
    result = update_webhook_info(req.db_id, req.webhook_id, req.webhook_status)
    
    if not result:
        raise HTTPException(status_code=404, detail="해당 ID의 데이터베이스를 찾을 수 없습니다.")
    
    return {
        "status": "updated",
        "db_id": req.db_id,
        "webhook_id": req.webhook_id
    }

# 중복된 엔드포인트 제거
@app.get("/get_db/{db_id}", response_model=DatabaseInfo)
def get_db(db_id: str):
    """특정 DB ID에 대한 정보를 반환합니다."""
    db_info = get_db_info_by_id(db_id)
    
    if not db_info:
        raise HTTPException(status_code=404, detail="데이터베이스를 찾을 수 없습니다.")
    
    return DatabaseInfo(
        db_id=db_id,
        title=db_info.get("title", ""),
        parent_page_id=db_info.get("parent_page_id", ""),
        status=db_info.get("status", "ready"),
        webhook_id=db_info.get("webhook_id"),
        webhook_status=db_info.get("webhook_status", "inactive"),
        last_used_date=db_info.get("last_used_date")
    )

@app.get("/get_webhook/{db_id}", response_model=WebhookInfo)
def get_webhook(db_id: str):
    """특정 DB ID에 대한 웹훅 정보를 반환합니다."""
    webhook_info = get_webhook_info_by_db_id(db_id)
    
    if not webhook_info:
        return WebhookInfo(db_id=db_id)
    
    return WebhookInfo(
        db_id=db_id,
        webhook_id=webhook_info.get("webhook_id", ""),
        webhook_status=webhook_info.get("webhook_status", "inactive")
    )

#db 상태 업데이트(학습 대기중, 학습중, 학습완료)
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

# 모든 학습db목록
@app.get("/list_all_dbs")
def list_all_dbs(status: str = None):
    """모든 학습 DB 목록 조회"""
    return list_all_learning_databases(status)

@app.get("/list_db_in_page")
def list_db_in_page(parent_page_id: str):
    """페이지 내 DB 목록 조회"""
    return list_databases_in_page(parent_page_id)

@app.post("/verify_webhooks", response_model=Dict[str, Any])
async def verify_webhooks():
    """모든 활성 웹훅의 상태를 검증합니다."""
    result = await verify_all_webhooks()
    return result

@app.post("/retry_failed_operations", response_model=Dict[str, Any])
async def retry_failed_operations():
    """실패한 웹훅 작업을 재시도합니다."""
    result = await retry_failed_webhook_operations()
    return result

@app.get("/list_dbs", response_model=Dict[str, List[DatabaseInfo]])
def list_dbs():
    """모든 학습 데이터베이스 목록을 반환합니다."""
    databases = list_all_learning_databases()
    result = []
    
    for db in databases:
        result.append(DatabaseInfo(
            db_id=db.get("db_id", ""),
            title=db.get("title", ""),
            parent_page_id=db.get("parent_page_id", ""),
            status=db.get("status", "ready"),
            webhook_id=db.get("webhook_id"),
            webhook_status=db.get("webhook_status", "inactive"),
            last_used_date=db.get("last_used_date")
        ))
    
    return {"databases": result}

@app.get("/current_db", response_model=Optional[DatabaseInfo])
def current_db():
    """현재 사용 중인 학습 데이터베이스 정보를 반환합니다."""
    db_info = get_current_learning_database_info()
    
    if not db_info:
        return None
    
    return DatabaseInfo(
        db_id=db_info.get("db_id", ""),
        title=db_info.get("title", ""),
        parent_page_id=db_info.get("parent_page_id", ""),
        status=db_info.get("status", "ready"),
        webhook_id=db_info.get("webhook_id"),
        webhook_status=db_info.get("webhook_status", "inactive"),
        last_used_date=db_info.get("last_used_date")
    )

@app.get("/list_dbs_in_page/{page_id}")
def list_dbs_in_page(page_id: str):
    """특정 페이지 내의 데이터베이스 목록을 반환합니다."""
    databases = get_databases_in_page(page_id)
    
    if not databases:
        return {"error": "데이터베이스를 찾을 수 없거나 액세스할 수 없습니다."}
    
    return {"databases": databases}

@app.post("/register_db")
def register_db(req: Dict[str, Any]):
    """새로운 학습 데이터베이스를 등록합니다."""
    parent_page_id = req.get("parent_page_id")
    db_id = req.get("db_id")
    title = req.get("title")
    
    if not parent_page_id or not db_id or not title:
        return {"error": "필수 파라미터가 누락되었습니다."}
    
    success = insert_learning_database(db_id, title, parent_page_id)
    
    if not success:
        return {"error": "데이터베이스 등록에 실패했습니다."}
    
    return {"status": "registered"}

@app.post("/activate_db/{db_id}")
def activate_db(db_id: str):
    """학습 데이터베이스를 활성화합니다."""
    success = activate_database(db_id)
    
    if not success:
        return {"error": "데이터베이스 활성화에 실패했습니다."}
    
    return {"status": "activated"}

@app.post("/deactivate_db/{db_id}")
def deactivate_db(db_id: str, req: Dict[str, Any] = None):
    """학습 데이터베이스를 비활성화합니다."""
    end_status = False
    if req and "end_status" in req:
        end_status = req["end_status"]
    
    success = deactivate_database(db_id, end_status)
    
    if not success:
        return {"error": "데이터베이스 비활성화에 실패했습니다."}
    
    return {"status": "deactivated"}

@app.post("/monitor_all")
async def monitor_all():
    """모든 학습 데이터베이스의 감시를 시작합니다."""
    try:
        # 모든 학습 DB 목록 조회
        databases = list_all_learning_databases()
        total = len(databases)
        success = 0
        skipped = 0
        failed = 0
        
        for db in databases:
            db_id = db.get("db_id")
            # 이미 활성화된 웹훅이 있는 경우 스킵
            if db.get("webhook_status") == "active":
                skipped += 1
                continue
            
            # 웹훅 생성 요청
            try:
                webhook_url = os.environ.get("WEBHOOK_CREATE_URL", "https://hook.eu2.make.com/YOUR_MAKE_WEBHOOK_ID")
                async with httpx.AsyncClient() as client:
                    response = await client.post(webhook_url, json={"db_id": db_id}, timeout=30.0)
                    response.raise_for_status()
                
                # 작업 로그 기록
                log_webhook_operation(db_id, "create", "success")
                success += 1
            except Exception as e:
                # 실패 로그 기록
                log_webhook_operation(db_id, "create", "failed", str(e))
                failed += 1
        
        return {
            "total": total,
            "success": success,
            "skipped": skipped,
            "failed": failed
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/unmonitor_all")
async def unmonitor_all():
    """모든 학습 데이터베이스의 감시를 중지합니다."""
    try:
        # 활성화된 모든 웹훅 조회
        databases = list_all_learning_databases()
        active_dbs = [db for db in databases if db.get("webhook_status") == "active"]
        total = len(active_dbs)
        success = 0
        failed = 0
        
        for db in active_dbs:
            db_id = db.get("db_id")
            webhook_id = db.get("webhook_id")
            
            # 웹훅 삭제 요청
            try:
                webhook_url = os.environ.get("WEBHOOK_DELETE_URL", "https://hook.eu2.make.com/YOUR_MAKE_WEBHOOK_DELETE_ID")
                async with httpx.AsyncClient() as client:
                    response = await client.post(webhook_url, json={"db_id": db_id}, timeout=30.0)
                    response.raise_for_status()
                
                # 웹훅 정보 초기화
                update_webhook_info(db_id, "", "inactive")
                
                # 작업 로그 기록
                log_webhook_operation(db_id, "delete", "success", None, webhook_id)
                success += 1
            except Exception as e:
                # 실패 로그 기록
                log_webhook_operation(db_id, "delete", "failed", str(e), webhook_id)
                failed += 1
        
        return {
            "total": total,
            "success": success,
            "failed": failed
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "message": "Notion Learning API",
        "version": settings.VERSION,
        "docs_url": "/docs"
    }