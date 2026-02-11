import uuid
from datetime import datetime

from pydantic import BaseModel


class PlanningMessageResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    sequence: int
    role: str
    content: str
    is_streaming: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PlanningUserMessage(BaseModel):
    content: str
