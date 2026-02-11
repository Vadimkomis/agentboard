from httpx import AsyncClient

from src.models.user import User


async def test_get_me(auth_client: AsyncClient, user: User):
    resp = await auth_client.get("/api/users/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["login"] == user.login
    assert data["name"] == user.name
    assert data["email"] == user.email
    assert data["plan_tier"] == "free"
    assert "id" in data


async def test_keys_status_no_keys(auth_client: AsyncClient):
    resp = await auth_client.get("/api/users/me/keys/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["anthropic_key_set"] is False
    assert data["openai_key_set"] is False


async def test_save_anthropic_key(auth_client: AsyncClient):
    resp = await auth_client.patch(
        "/api/users/me/keys",
        json={"anthropic_key": "sk-ant-test-key"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify status reflects the change
    status_resp = await auth_client.get("/api/users/me/keys/status")
    data = status_resp.json()
    assert data["anthropic_key_set"] is True
    assert data["openai_key_set"] is False


async def test_save_openai_key(auth_client: AsyncClient):
    resp = await auth_client.patch(
        "/api/users/me/keys",
        json={"openai_key": "sk-test-openai-key"},
    )
    assert resp.status_code == 200

    status_resp = await auth_client.get("/api/users/me/keys/status")
    data = status_resp.json()
    assert data["openai_key_set"] is True


async def test_save_both_keys(auth_client: AsyncClient):
    resp = await auth_client.patch(
        "/api/users/me/keys",
        json={
            "anthropic_key": "sk-ant-key",
            "openai_key": "sk-openai-key",
        },
    )
    assert resp.status_code == 200

    status_resp = await auth_client.get("/api/users/me/keys/status")
    data = status_resp.json()
    assert data["anthropic_key_set"] is True
    assert data["openai_key_set"] is True


async def test_clear_key_by_sending_empty(auth_client: AsyncClient):
    # First set a key
    await auth_client.patch(
        "/api/users/me/keys",
        json={"anthropic_key": "sk-ant-key"},
    )

    # Then clear it
    await auth_client.patch(
        "/api/users/me/keys",
        json={"anthropic_key": ""},
    )

    status_resp = await auth_client.get("/api/users/me/keys/status")
    assert status_resp.json()["anthropic_key_set"] is False
