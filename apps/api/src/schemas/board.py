import uuid
from datetime import datetime

from pydantic import BaseModel


class BoardColumnResponse(BaseModel):
    id: uuid.UUID
    name: str
    position: int
    ticket_status: str

    model_config = {"from_attributes": True}


class BoardResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    columns: list[BoardColumnResponse]
    created_at: datetime

    model_config = {"from_attributes": True}
