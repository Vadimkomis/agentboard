import uuid
from datetime import datetime

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    repo_full_name: str
    repo_url: str
    default_branch: str = "main"


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    default_branch: str | None = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    repo_full_name: str
    repo_url: str
    default_branch: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
