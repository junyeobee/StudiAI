from strenum import StrEnum
from typing import TypedDict, Callable, Any
from pydantic import BaseModel

class Group(StrEnum):
    PAGE = "learning/pages"
    DB = "databases"
    WEB = "webhooks"
    NOTION_SETTINGS = "notion_setting"
    AUTH = "auth"
    GITHUB_WEBHOOK = "github_webhook"
    FEEDBACK = "feedback"

class Route(TypedDict):
    method: str
    path: Callable[[dict[str, Any]], str]
    needs_json: bool

class GitHubWebhookCreate(BaseModel):
    repo_url: str
    learning_db_id: str
    events: list[str] = ["push"] 