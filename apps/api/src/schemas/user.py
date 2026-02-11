import uuid
from datetime import datetime

from pydantic import BaseModel


class UserResponse(BaseModel):
    id: uuid.UUID
    github_id: int
    login: str
    name: str | None
    email: str | None
    avatar_url: str | None
    plan_tier: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateKeys(BaseModel):
    anthropic_key: str | None = None
    openai_key: str | None = None
