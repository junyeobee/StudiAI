from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

# 상태 Enum
class WorkspaceStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

# 조회 결과 모델
class UserWorkspace(BaseModel):
    """사용자 워크스페이스 정보"""
    user_id: str = Field(..., description="사용자 ID")
    workspace_id: str = Field(..., description="워크스페이스 ID")
    workspace_name: str = Field(..., description="워크스페이스 이름")
    provider: str = Field("notion", description="서비스 제공자")
    status: WorkspaceStatus = Field(..., description="워크스페이스 상태")
    
    class Config:
        from_attributes = True

# 워크스페이스 목록 응답
class UserWorkspaceList(BaseModel):
    """사용자 워크스페이스 목록"""
    workspaces: List[UserWorkspace]

# 워크스페이스 상태 변경 요청
class WorkspaceStatusUpdate(BaseModel):
    """워크스페이스 상태 변경 요청"""
    user_id: str = Field(..., description="소유주")
    workspace_id: str = Field(..., description="워크스페이스 ID")