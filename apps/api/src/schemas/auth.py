from pydantic import BaseModel


class GitHubAuthRequest(BaseModel):
    github_token: str
    github_id: int
    login: str
    name: str | None = None
    email: str | None = None
    avatar_url: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
