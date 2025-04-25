"""
학습 서비스
"""
from typing import List, Optional
from datetime import datetime
from app.models.learning import (
    LearningPlan,
    LearningPlanCreate,
    LearningPlanUpdate,
    LearningStatus,
    LearningSummary
)
from app.core.exceptions import LearningError
from app.utils.logger import api_logger
from app.core.config import settings
from notion_client import Client

class LearningService:
    def __init__(self):
        self.notion = Client(auth=settings.NOTION_API_KEY)
        self.api_logger = api_logger

    async def create_learning_plan(self, db_id: str, plan: LearningPlanCreate) -> LearningPlan:
        """새로운 학습 계획 생성"""
        try:
            # Notion API를 통해 페이지 생성
            response = await self.notion.pages.create(
                parent={"database_id": db_id},
                properties={
                    "Name": {
                        "title": [
                            {
                                "text": {
                                    "content": plan.title
                                }
                            }
                        ]
                    },
                    "Description": {
                        "rich_text": [
                            {
                                "text": {
                                    "content": plan.description or ""
                                }
                            }
                        ]
                    },
                    "Status": {
                        "select": {
                            "name": LearningStatus.PLANNED
                        }
                    },
                    "Start Date": {
                        "date": {
                            "start": plan.start_date.isoformat() if plan.start_date else None
                        }
                    },
                    "End Date": {
                        "date": {
                            "start": plan.end_date.isoformat() if plan.end_date else None
                        }
                    }
                }
            )
            
            # 학습 계획 정보 생성
            learning_plan = LearningPlan(
                page_id=response["id"],
                db_id=db_id,
                title=plan.title,
                description=plan.description,
                status=LearningStatus.PLANNED,
                start_date=plan.start_date,
                end_date=plan.end_date
            )
            
            self.api_logger.info(f"학습 계획 생성 성공: {learning_plan.page_id}")
            return learning_plan
            
        except Exception as e:
            self.api_logger.error(f"학습 계획 생성 실패: {str(e)}")
            raise LearningError(f"학습 계획 생성 실패: {str(e)}")

    async def update_learning_plan(self, page_id: str, plan: LearningPlanUpdate) -> LearningPlan:
        """학습 계획 업데이트"""
        try:
            # 현재 학습 계획 조회
            current_plan = await self.get_learning_plan(page_id)
            
            # 업데이트할 필드만 선택
            update_data = plan.dict(exclude_unset=True)
            
            # Notion API를 통해 페이지 업데이트
            properties = {}
            if "title" in update_data:
                properties["Name"] = {
                    "title": [
                        {
                            "text": {
                                "content": update_data["title"]
                            }
                        }
                    ]
                }
            if "description" in update_data:
                properties["Description"] = {
                    "rich_text": [
                        {
                            "text": {
                                "content": update_data["description"] or ""
                            }
                        }
                    ]
                }
            if "status" in update_data:
                properties["Status"] = {
                    "select": {
                        "name": update_data["status"]
                    }
                }
            if "start_date" in update_data:
                properties["Start Date"] = {
                    "date": {
                        "start": update_data["start_date"].isoformat() if update_data["start_date"] else None
                    }
                }
            if "end_date" in update_data:
                properties["End Date"] = {
                    "date": {
                        "start": update_data["end_date"].isoformat() if update_data["end_date"] else None
                    }
                }
            
            await self.notion.pages.update(
                page_id=page_id,
                properties=properties
            )
            
            # 학습 계획 정보 업데이트
            updated_plan = LearningPlan(
                **current_plan.dict(),
                **update_data,
                updated_at=datetime.now()
            )
            
            self.api_logger.info(f"학습 계획 업데이트 성공: {page_id}")
            return updated_plan
            
        except Exception as e:
            self.api_logger.error(f"학습 계획 업데이트 실패: {str(e)}")
            raise LearningError(f"학습 계획 업데이트 실패: {str(e)}")

    async def get_learning_plan(self, page_id: str) -> LearningPlan:
        """학습 계획 조회"""
        try:
            # Notion API를 통해 페이지 조회
            response = await self.notion.pages.retrieve(page_id=page_id)
            
            # 학습 계획 정보 생성
            properties = response["properties"]
            learning_plan = LearningPlan(
                page_id=response["id"],
                db_id=response["parent"]["database_id"],
                title=properties["Name"]["title"][0]["text"]["content"],
                description=properties["Description"]["rich_text"][0]["text"]["content"] if properties["Description"]["rich_text"] else None,
                status=properties["Status"]["select"]["name"],
                start_date=datetime.fromisoformat(properties["Start Date"]["date"]["start"]) if properties["Start Date"]["date"] else None,
                end_date=datetime.fromisoformat(properties["End Date"]["date"]["start"]) if properties["End Date"]["date"] else None,
                created_at=datetime.fromisoformat(response["created_time"]),
                updated_at=datetime.fromisoformat(response["last_edited_time"])
            )
            
            self.api_logger.info(f"학습 계획 조회 성공: {page_id}")
            return learning_plan
            
        except Exception as e:
            self.api_logger.error(f"학습 계획 조회 실패: {str(e)}")
            raise LearningError(f"학습 계획 조회 실패: {str(e)}")

    async def get_learning_plans(self, db_id: str) -> List[LearningPlan]:
        """데이터베이스의 모든 학습 계획 조회"""
        try:
            # Notion API를 통해 데이터베이스 쿼리
            response = await self.notion.databases.query(
                database_id=db_id,
                sorts=[
                    {
                        "property": "Created",
                        "direction": "descending"
                    }
                ]
            )
            
            # 학습 계획 목록 생성
            learning_plans = []
            for page in response["results"]:
                properties = page["properties"]
                learning_plan = LearningPlan(
                    page_id=page["id"],
                    db_id=db_id,
                    title=properties["Name"]["title"][0]["text"]["content"],
                    description=properties["Description"]["rich_text"][0]["text"]["content"] if properties["Description"]["rich_text"] else None,
                    status=properties["Status"]["select"]["name"],
                    start_date=datetime.fromisoformat(properties["Start Date"]["date"]["start"]) if properties["Start Date"]["date"] else None,
                    end_date=datetime.fromisoformat(properties["End Date"]["date"]["start"]) if properties["End Date"]["date"] else None,
                    created_at=datetime.fromisoformat(page["created_time"]),
                    updated_at=datetime.fromisoformat(page["last_edited_time"])
                )
                learning_plans.append(learning_plan)
            
            self.api_logger.info(f"학습 계획 목록 조회 성공: {db_id}")
            return learning_plans
            
        except Exception as e:
            self.api_logger.error(f"학습 계획 목록 조회 실패: {str(e)}")
            raise LearningError(f"학습 계획 목록 조회 실패: {str(e)}")

    async def create_learning_summary(self, page_id: str, summary: str) -> LearningSummary:
        """학습 요약 생성"""
        try:
            # Notion API를 통해 블록 추가
            await self.notion.blocks.children.append(
                block_id=page_id,
                children=[
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {
                                        "content": summary
                                    }
                                }
                            ]
                        }
                    }
                ]
            )
            
            # 학습 요약 정보 생성
            learning_summary = LearningSummary(
                page_id=page_id,
                summary=summary
            )
            
            self.api_logger.info(f"학습 요약 생성 성공: {page_id}")
            return learning_summary
            
        except Exception as e:
            self.api_logger.error(f"학습 요약 생성 실패: {str(e)}")
            raise LearningError(f"학습 요약 생성 실패: {str(e)}")

    async def get_learning_summary(self, page_id: str) -> Optional[LearningSummary]:
        """학습 요약 조회"""
        try:
            # Notion API를 통해 블록 조회
            response = await self.notion.blocks.children.list(block_id=page_id)
            
            # 마지막 단락 블록 찾기
            summary = None
            for block in response["results"]:
                if block["type"] == "paragraph":
                    summary = block["paragraph"]["rich_text"][0]["text"]["content"]
            
            if not summary:
                return None
            
            # 학습 요약 정보 생성
            learning_summary = LearningSummary(
                page_id=page_id,
                summary=summary
            )
            
            self.api_logger.info(f"학습 요약 조회 성공: {page_id}")
            return learning_summary
            
        except Exception as e:
            self.api_logger.error(f"학습 요약 조회 실패: {str(e)}")
            raise LearningError(f"학습 요약 조회 실패: {str(e)}") 