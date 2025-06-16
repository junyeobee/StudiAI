from pydantic import BaseModel

class FeedbackRequest(BaseModel):
    message: str