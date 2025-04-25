from pydantic import BaseModel
from typing import Optional, Dict, Any

class NotionDatabase(BaseModel):
    id: str
    title: str
    parent_page_id: Optional[str] = None
    properties: Dict[str, Any] = {}

class NotionPage(BaseModel):
    id: str
    title: str
    parent_database_id: Optional[str] = None
    properties: Dict[str, Any] = {} 