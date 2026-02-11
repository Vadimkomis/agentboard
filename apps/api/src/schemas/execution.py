import uuid
from datetime import datetime

from pydantic import BaseModel


class ExecutionResponse(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    agent_type: str
    runtime: str
    status: str
    session_id: str | None
    total_tokens: int
    total_cost: float
    duration_seconds: int | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    error_message: str | None

    model_config = {"from_attributes": True}


class ExecutionLogResponse(BaseModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    sequence: int
    log_type: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}
