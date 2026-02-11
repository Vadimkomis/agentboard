import uuid

from httpx import AsyncClient

from src.auth import create_access_token
from src.models.user import User


async def test_create_access_token():
    user_id = uuid.uuid4()
    token = create_access_token(user_id)
    assert isinstance(token, str)
    assert len(token) > 0


async def test_get_me_authenticated(auth_client: AsyncClient, user: User):
    resp = await auth_client.get("/api/users/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["login"] == "testuser"
    assert data["email"] == "test@example.com"
    assert data["plan_tier"] == "free"


async def test_get_me_unauthenticated(unauth_client: AsyncClient):
    resp = await unauth_client.get("/api/users/me")
    assert resp.status_code == 403  # No bearer token


async def test_get_me_invalid_token(unauth_client: AsyncClient):
    unauth_client.headers["Authorization"] = "Bearer invalid-token"
    resp = await unauth_client.get("/api/users/me")
    assert resp.status_code == 401
