"""
데이터베이스 서비스
"""
from typing import List, Optional
from datetime import datetime
from app.models.database import DatabaseInfo, DatabaseCreate, DatabaseUpdate, DatabaseStatus
from app.core.exceptions import DatabaseError
from app.utils.logger import api_logger
from app.core.config import settings
from notion_client import Client

class DatabaseService:
    def __init__(self):
        self.notion = Client(auth=settings.NOTION_API_KEY)
        self.api_logger = api_logger

    async def create_database(self, db_create: DatabaseCreate) -> DatabaseInfo:
        """새로운 데이터베이스 생성"""
        try:
            # Notion API를 통해 데이터베이스 생성
            response = await self.notion.databases.create(
                parent={"page_id": db_create.parent_page_id},
                title=[{"type": "text", "text": {"content": db_create.title}}],
                properties={
                    "Name": {"title": {}},
                    "Status": {"select": {}},
                    "Created": {"date": {}},
                    "Updated": {"date": {}}
                }
            )
            
            # 데이터베이스 정보 생성
            db_info = DatabaseInfo(
                db_id=response["id"],
                title=db_create.title,
                parent_page_id=db_create.parent_page_id,
                status=DatabaseStatus.READY
            )
            
            self.api_logger.info(f"데이터베이스 생성 성공: {db_info.db_id}")
            return db_info
            
        except Exception as e:
            self.api_logger.error(f"데이터베이스 생성 실패: {str(e)}")
            raise DatabaseError(f"데이터베이스 생성 실패: {str(e)}")

    async def get_database(self, db_id: str) -> DatabaseInfo:
        """데이터베이스 정보 조회"""
        try:
            # Notion API를 통해 데이터베이스 정보 조회
            response = await self.notion.databases.retrieve(database_id=db_id)
            
            # 데이터베이스 정보 생성
            db_info = DatabaseInfo(
                db_id=response["id"],
                title=response["title"][0]["text"]["content"],
                parent_page_id=response["parent"]["page_id"],
                status=DatabaseStatus.READY  # TODO: 실제 상태 조회 구현
            )
            
            self.api_logger.info(f"데이터베이스 조회 성공: {db_id}")
            return db_info
            
        except Exception as e:
            self.api_logger.error(f"데이터베이스 조회 실패: {str(e)}")
            raise DatabaseError(f"데이터베이스 조회 실패: {str(e)}")

    async def update_database(self, db_id: str, db_update: DatabaseUpdate) -> DatabaseInfo:
        """데이터베이스 정보 업데이트"""
        try:
            # 현재 데이터베이스 정보 조회
            current_db = await self.get_database(db_id)
            
            # 업데이트할 필드만 선택
            update_data = db_update.dict(exclude_unset=True)
            
            # Notion API를 통해 데이터베이스 업데이트
            if "title" in update_data:
                await self.notion.databases.update(
                    database_id=db_id,
                    title=[{"type": "text", "text": {"content": update_data["title"]}}]
                )
            
            # 데이터베이스 정보 업데이트
            updated_db = DatabaseInfo(
                **current_db.dict(),
                **update_data
            )
            
            self.api_logger.info(f"데이터베이스 업데이트 성공: {db_id}")
            return updated_db
            
        except Exception as e:
            self.api_logger.error(f"데이터베이스 업데이트 실패: {str(e)}")
            raise DatabaseError(f"데이터베이스 업데이트 실패: {str(e)}")

    async def list_databases(self) -> List[DatabaseInfo]:
        """모든 데이터베이스 목록 조회"""
        try:
            # TODO: Supabase에서 데이터베이스 목록 조회 구현
            return []
            
        except Exception as e:
            self.api_logger.error(f"데이터베이스 목록 조회 실패: {str(e)}")
            raise DatabaseError(f"데이터베이스 목록 조회 실패: {str(e)}")

    async def activate_database(self, db_id: str) -> DatabaseInfo:
        """데이터베이스 활성화"""
        try:
            # 현재 활성화된 데이터베이스 비활성화
            # TODO: Supabase에서 활성화된 데이터베이스 조회 및 비활성화
            
            # 새로운 데이터베이스 활성화
            db_info = await self.get_database(db_id)
            updated_db = await self.update_database(
                db_id,
                DatabaseUpdate(status=DatabaseStatus.USED)
            )
            
            self.api_logger.info(f"데이터베이스 활성화 성공: {db_id}")
            return updated_db
            
        except Exception as e:
            self.api_logger.error(f"데이터베이스 활성화 실패: {str(e)}")
            raise DatabaseError(f"데이터베이스 활성화 실패: {str(e)}")

    async def deactivate_database(self, db_id: str) -> DatabaseInfo:
        """데이터베이스 비활성화"""
        try:
            # 데이터베이스 비활성화
            updated_db = await self.update_database(
                db_id,
                DatabaseUpdate(status=DatabaseStatus.READY)
            )
            
            self.api_logger.info(f"데이터베이스 비활성화 성공: {db_id}")
            return updated_db
            
        except Exception as e:
            self.api_logger.error(f"데이터베이스 비활성화 실패: {str(e)}")
            raise DatabaseError(f"데이터베이스 비활성화 실패: {str(e)}") 