import uuid

from httpx import ASGITransport, AsyncClient

from src.auth import create_access_token
from src.main import app
from src.models.user import User


async def test_list_teams_empty(auth_client: AsyncClient):
    resp = await auth_client.get("/api/teams")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_team(auth_client: AsyncClient):
    resp = await auth_client.post(
        "/api/teams",
        json={"name": "My Team", "slug": "my-team"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Team"
    assert data["slug"] == "my-team"
    assert data["plan_tier"] == "free"
    assert data["execution_quota"] == 50


async def test_create_team_duplicate_slug(auth_client: AsyncClient):
    await auth_client.post(
        "/api/teams",
        json={"name": "Team 1", "slug": "unique-slug"},
    )
    resp = await auth_client.post(
        "/api/teams",
        json={"name": "Team 2", "slug": "unique-slug"},
    )
    assert resp.status_code == 400
    assert "slug" in resp.json()["detail"].lower()


async def test_list_teams_after_create(auth_client: AsyncClient):
    await auth_client.post(
        "/api/teams",
        json={"name": "Alpha", "slug": "alpha"},
    )
    resp = await auth_client.get("/api/teams")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_get_team(auth_client: AsyncClient):
    create_resp = await auth_client.post(
        "/api/teams",
        json={"name": "Get Test", "slug": "get-test"},
    )
    team_id = create_resp.json()["id"]

    resp = await auth_client.get(f"/api/teams/{team_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Get Test"


async def test_get_nonexistent_team(auth_client: AsyncClient):
    resp = await auth_client.get(f"/api/teams/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_list_members(auth_client: AsyncClient):
    create_resp = await auth_client.post(
        "/api/teams",
        json={"name": "Members Test", "slug": "members-test"},
    )
    team_id = create_resp.json()["id"]

    resp = await auth_client.get(f"/api/teams/{team_id}/members")
    assert resp.status_code == 200
    members = resp.json()
    assert len(members) == 1  # Owner is auto-added
    assert members[0]["role"] == "owner"


async def test_invite_member(
    auth_client: AsyncClient,
    second_user: User,
):
    create_resp = await auth_client.post(
        "/api/teams",
        json={"name": "Invite Test", "slug": "invite-test"},
    )
    team_id = create_resp.json()["id"]

    resp = await auth_client.post(
        f"/api/teams/{team_id}/members",
        json={"user_id": str(second_user.id), "role": "member"},
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "member"

    # Verify member count
    members_resp = await auth_client.get(f"/api/teams/{team_id}/members")
    assert len(members_resp.json()) == 2


async def test_invite_duplicate_member(
    auth_client: AsyncClient,
    second_user: User,
):
    create_resp = await auth_client.post(
        "/api/teams",
        json={"name": "Dup Test", "slug": "dup-test"},
    )
    team_id = create_resp.json()["id"]

    await auth_client.post(
        f"/api/teams/{team_id}/members",
        json={"user_id": str(second_user.id)},
    )

    # Try inviting again
    resp = await auth_client.post(
        f"/api/teams/{team_id}/members",
        json={"user_id": str(second_user.id)},
    )
    assert resp.status_code == 400


async def test_remove_member(
    auth_client: AsyncClient,
    second_user: User,
):
    create_resp = await auth_client.post(
        "/api/teams",
        json={"name": "Remove Test", "slug": "remove-test"},
    )
    team_id = create_resp.json()["id"]

    await auth_client.post(
        f"/api/teams/{team_id}/members",
        json={"user_id": str(second_user.id)},
    )

    resp = await auth_client.delete(
        f"/api/teams/{team_id}/members/{second_user.id}"
    )
    assert resp.status_code == 204

    members_resp = await auth_client.get(f"/api/teams/{team_id}/members")
    assert len(members_resp.json()) == 1


async def test_cannot_remove_owner(
    auth_client: AsyncClient,
    user: User,
):
    create_resp = await auth_client.post(
        "/api/teams",
        json={"name": "Owner Test", "slug": "owner-test"},
    )
    team_id = create_resp.json()["id"]

    resp = await auth_client.delete(
        f"/api/teams/{team_id}/members/{user.id}"
    )
    assert resp.status_code == 400


async def test_member_cannot_invite(
    auth_client: AsyncClient,
    user: User,
    second_user: User,
):
    """A 'member' role should not be able to invite others."""
    create_resp = await auth_client.post(
        "/api/teams",
        json={"name": "Perms Test", "slug": "perms-test"},
    )
    team_id = create_resp.json()["id"]

    # Add second_user as member
    await auth_client.post(
        f"/api/teams/{team_id}/members",
        json={"user_id": str(second_user.id), "role": "member"},
    )

    # Try to invite as second_user (member role)
    token = create_access_token(second_user.id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client2:
        client2.headers["Authorization"] = f"Bearer {token}"
        # Create a third user UUID (doesn't exist, but tests the permission check first)
        resp = await client2.post(
            f"/api/teams/{team_id}/members",
            json={"user_id": str(uuid.uuid4()), "role": "member"},
        )
        assert resp.status_code == 403
