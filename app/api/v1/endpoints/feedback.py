from fastapi import APIRouter, Depends
from app.services.supa import send_feedback
from app.api.v1.dependencies.auth import require_user
from app.core.supabase_connect import get_supabase
from supabase._async.client import AsyncClient
from app.models.feedback import FeedbackRequest

router = APIRouter()

@router.post("/")
async def create_feedback(feedback: FeedbackRequest, user_id: str = Depends(require_user), supabase: AsyncClient = Depends(get_supabase)):
    """
    사용자 피드백 제출
    """
    result = await send_feedback(
        message=feedback.message,
        user_id=user_id,
        supabase=supabase
    )
    
    return {"status": "success", "feedback_id": result[0]["id"]}