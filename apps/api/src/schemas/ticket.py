import uuid
from datetime import datetime

from pydantic import BaseModel


class TicketCreate(BaseModel):
    title: str
    description: str | None = None
    column_id: uuid.UUID


class TicketUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    column_id: uuid.UUID | None = None
    position: int | None = None
    status: str | None = None
    agent_type: str | None = None
    runtime: str | None = None
    priority: str | None = None
    complexity: str | None = None


class TicketMoveRequest(BaseModel):
    column_id: uuid.UUID
    position: int


class TicketTransitionRequest(BaseModel):
    status: str


class TriageResult(BaseModel):
    agent_type: str
    runtime: str
    priority: str
    complexity: str
    branch_name: str
    refined_description: str
    acceptance_criteria: str
    context_files: list[str]
    reasoning: str


class TicketResponse(BaseModel):
    id: uuid.UUID
    column_id: uuid.UUID
    project_id: uuid.UUID
    created_by_id: uuid.UUID
    title: str
    description: str | None
    position: int
    status: str
    agent_type: str | None
    runtime: str | None
    priority: str | None
    complexity: str | None
    refined_description: str | None
    acceptance_criteria: str | None
    context_files: dict | None
    triage_reasoning: str | None
    branch_name: str | None
    pr_url: str | None
    pr_number: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
