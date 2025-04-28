"""
학습 서비스
"""
from typing import List, Optional
from datetime import datetime
from app.models.learning import (
    LearningPlan,
    LearningPageCreate,
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
    
    async def create_learning_page(self, database_id: str, plan: LearningPageCreate) -> str:
        """Notion에 단일 학습 페이지 생성"""
        props = {
            "학습 제목": {
                "title": [{"text": {"content": plan.title}}]
            },
            "날짜": {
                "date": {"start": plan.date.isoformat()}
            },
            "진행 상태": {
                "select": {"name": plan.status.value}
            },
            "복습 여부": {
                "checkbox": plan.revisit
            }
        }

        resp = await self._make_request(
            "POST",
            "pages",
            json={
                "parent": {"database_id": database_id},
                "properties": props
            }
        )
        return resp["id"]

    async def update_learning_plan(self, page_id: str, plan: LearningPlanUpdate) -> LearningPlan:
        """학습 계획 업데이트"""
        try:
            current = await self.get_learning_plan(page_id)
            update_data = plan.model_dump(exclude_unset=True)
            props: dict = {}

            if "title" in update_data:
                props["학습 제목"] = {
                    "title": [{"text": {"content": update_data["title"]}}]
                }
            if "description" in update_data:
                props["설명"] = {
                    "rich_text": [{"text": {"content": update_data["description"] or ""}}]
                }
            if "status" in update_data:
                props["진행 상태"] = {
                    "select": {"name": update_data["status"].value}
                }
            if "start_date" in update_data:
                sd = update_data["start_date"]
                props["시작일"] = {"date": {"start": sd.isoformat() if sd else None}}
            if "end_date" in update_data:
                ed = update_data["end_date"]
                props["종료일"] = {"date": {"start": ed.isoformat() if ed else None}}

            await self.notion.pages.update(page_id=page_id, properties=props)

            return LearningPlan(
                **current.model_dump(),
                **update_data,
                updated_at=datetime.now()
            )
        except Exception as e:
            self.api_logger.error(f"학습 계획 업데이트 실패: {e}")
            raise LearningError(f"학습 계획 업데이트 실패: {e}")

    async def get_learning_plan(self, page_id: str) -> LearningPlan:
        """학습 계획 조회"""
        try:
            resp = await self.notion.pages.retrieve(page_id=page_id)
            p = resp["properties"]
            lp = LearningPlan(
                page_id=resp["id"],
                db_id=resp["parent"]["database_id"],
                title=p["학습 제목"]["title"][0]["text"]["content"],
                description=(
                    p["설명"]["rich_text"][0]["text"]["content"]
                    if p["설명"]["rich_text"] else None
                ),
                status=LearningStatus(p["진행 상태"]["select"]["name"]),
                start_date=(
                    datetime.fromisoformat(p["시작일"]["date"]["start"])
                    if p.get("시작일") and p["시작일"]["date"] else None
                ),
                end_date=(
                    datetime.fromisoformat(p["종료일"]["date"]["start"])
                    if p.get("종료일") and p["종료일"]["date"] else None
                ),
                created_at=datetime.fromisoformat(resp["created_time"]),
                updated_at=datetime.fromisoformat(resp["last_edited_time"])
            )
            self.api_logger.info(f"학습 계획 조회 성공: {page_id}")
            return lp
        except Exception as e:
            self.api_logger.error(f"학습 계획 조회 실패: {e}")
            raise LearningError(f"학습 계획 조회 실패: {e}")

    async def get_learning_plans(self, db_id: str) -> List[LearningPlan]:
        """DB 내 모든 학습 계획 조회"""
        try:
            resp = await self.notion.databases.query(
                database_id=db_id,
                sorts=[{"property": "생성일", "direction": "descending"}]
            )
            plans: List[LearningPlan] = []
            for pg in resp["results"]:
                props = pg["properties"]
                plans.append(
                    LearningPlan(
                        page_id=pg["id"],
                        db_id=db_id,
                        title=props["학습 제목"]["title"][0]["text"]["content"],
                        description=(
                            props["설명"]["rich_text"][0]["text"]["content"]
                            if props["설명"]["rich_text"] else None
                        ),
                        status=LearningStatus(props["진행 상태"]["select"]["name"]),
                        start_date=(
                            datetime.fromisoformat(props["시작일"]["date"]["start"])
                            if props.get("시작일") and props["시작일"]["date"] else None
                        ),
                        end_date=(
                            datetime.fromisoformat(props["종료일"]["date"]["start"])
                            if props.get("종료일") and props["종료일"]["date"] else None
                        ),
                        created_at=datetime.fromisoformat(pg["created_time"]),
                        updated_at=datetime.fromisoformat(pg["last_edited_time"])
                    )
                )
            return plans
        except Exception as e:
            self.api_logger.error(f"학습 계획 목록 조회 실패: {e}")
            raise LearningError(f"학습 계획 목록 조회 실패: {e}")
