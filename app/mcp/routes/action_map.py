from app.mcp.models.api import Group, Route, GitHubWebhookCreate
from app.models.learning import LearningPagesRequest, PageUpdateRequest
from app.models.database import DatabaseCreate, DatabaseUpdate
from app.models.feedback import FeedbackRequest

def _const(s: str):
    """상수 경로 반환 람다 래퍼"""
    return lambda _p: s

# 각 endpoint에 대한 Action Map
ACTION_MAP: dict[Group, dict[str, Route]] = {
    Group.PAGE: {
        "list": {"method":"GET", "path":lambda p:f"?db_id={p['db_id']}" if p.get("db_id") else "?current=true", "needs_json":False},
        "create": {"method":"POST", "path":_const("/create"), "needs_json":True},
        "update": {"method":"PATCH", "path":lambda p:f"/{p['page_id']}", "needs_json":True},
        "delete": {"method":"DELETE", "path":lambda p:f"/{p['page_id']}", "needs_json":False},
        "get": {"method":"GET", "path":lambda p:f"/{p['page_id']}/content", "needs_json":False},
        "commits": {"method":"GET", "path":lambda p:f"/{p['page_id']}/commits", "needs_json":False},
        "commit_sha": {"method":"GET", "path":lambda p:f"/{p['page_id']}/commits/{p['commit_sha']}", "needs_json":False},
    },
    Group.DB: {
        "list": {"method":"GET", "path":_const("/available"), "needs_json":False},
        "current": {"method":"GET", "path":_const("/active"), "needs_json":False},
        "create": {"method":"POST", "path":_const("/"), "needs_json":True},
        "activate": {"method":"POST", "path":lambda p:f"/{p['db_id']}/activate", "needs_json":False},
        "deactivate": {"method":"POST", "path":_const("/deactivate"), "needs_json":False},
        "update": {"method":"PATCH", "path":lambda p:f"/{p['db_id']}", "needs_json":True},
    },
    Group.WEB: {
        "failed": {"method":"GET", "path":_const("/operations/failed"), "needs_json":False},
        "list": {"method":"GET", "path":_const("/operations"), "needs_json":False},
        "detail": {"method":"GET", "path":lambda p:f"/operations/{p['operation_id']}", "needs_json":False},
    },
    Group.NOTION_SETTINGS: {
        "workspaces": {"method":"GET", "path":_const("/workspaces"), "needs_json":False},
        "set_active_workspace": {"method":"POST", "path":lambda p:f"/workspaces/{p['workspace_id']}/active", "needs_json":True},
        "top_pages": {"method":"GET", "path":_const("/top-pages"), "needs_json":False},
        "set_top_page": {"method":"GET", "path":lambda p:f"/set-top-page/{p['page_id']}", "needs_json":False},
        "get_top_page": {"method":"GET", "path":_const("/get-top-page"), "needs_json":False},
    },
    Group.AUTH :{
        "get_token" : {"method":"GET", "path":lambda p:f"/oauth/{p['provider']}", "needs_json":False},
    },
    Group.GITHUB_WEBHOOK: {
        "create": {"method":"POST", "path":_const("/"), "needs_json":True},
        "repos": {"method":"GET", "path":_const("/repos"), "needs_json":False},
    },
    Group.FEEDBACK: {
        "send_feedback": {"method": "POST", "path": _const("/"), "needs_json": True},
    }
}

# Payload 검증이 필요한 액션과 Pydantic 모델 매핑
PAYLOAD_MODEL = {
    (Group.PAGE, "create"): LearningPagesRequest,
    (Group.PAGE, "update"): PageUpdateRequest,
    (Group.DB, "create"): DatabaseCreate,
    (Group.DB, "update"): DatabaseUpdate,
    (Group.GITHUB_WEBHOOK, "create"): GitHubWebhookCreate,
    (Group.FEEDBACK, "FEEDBACK"): FeedbackRequest,
} 