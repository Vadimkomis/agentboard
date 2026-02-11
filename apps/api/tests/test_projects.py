import uuid

from httpx import AsyncClient

from src.models.project import Project
from src.models.user import User


async def test_list_projects_empty(auth_client: AsyncClient):
    resp = await auth_client.get("/api/projects")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_project(auth_client: AsyncClient):
    resp = await auth_client.post(
        "/api/projects",
        json={
            "name": "My Project",
            "repo_full_name": "user/repo",
            "repo_url": "https://github.com/user/repo",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Project"
    assert data["repo_full_name"] == "user/repo"
    assert data["default_branch"] == "main"
    assert "id" in data


async def test_create_and_list_projects(auth_client: AsyncClient):
    # Create two projects
    await auth_client.post(
        "/api/projects",
        json={
            "name": "Project A",
            "repo_full_name": "user/repo-a",
            "repo_url": "https://github.com/user/repo-a",
        },
    )
    await auth_client.post(
        "/api/projects",
        json={
            "name": "Project B",
            "repo_full_name": "user/repo-b",
            "repo_url": "https://github.com/user/repo-b",
        },
    )

    resp = await auth_client.get("/api/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert {p["name"] for p in data} == {"Project A", "Project B"}


async def test_get_project(auth_client: AsyncClient, project: Project):
    resp = await auth_client.get(f"/api/projects/{project.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Test Project"
    assert data["repo_full_name"] == "testuser/test-repo"


async def test_get_nonexistent_project(auth_client: AsyncClient):
    fake_id = uuid.uuid4()
    resp = await auth_client.get(f"/api/projects/{fake_id}")
    assert resp.status_code == 404


async def test_update_project(auth_client: AsyncClient, project: Project):
    resp = await auth_client.patch(
        f"/api/projects/{project.id}",
        json={"name": "Updated Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"


async def test_delete_project(auth_client: AsyncClient, project: Project):
    resp = await auth_client.delete(f"/api/projects/{project.id}")
    assert resp.status_code == 204

    # Verify it's gone
    resp = await auth_client.get(f"/api/projects/{project.id}")
    assert resp.status_code == 404


async def test_project_creates_default_board(auth_client: AsyncClient):
    """When a project is created, it should auto-create a board with 6 columns."""
    resp = await auth_client.post(
        "/api/projects",
        json={
            "name": "Board Test",
            "repo_full_name": "user/board-test",
            "repo_url": "https://github.com/user/board-test",
        },
    )
    project_id = resp.json()["id"]

    boards_resp = await auth_client.get(f"/api/projects/{project_id}/boards")
    assert boards_resp.status_code == 200
    boards = boards_resp.json()
    assert len(boards) == 1
    assert boards[0]["name"] == "Main Board"
    assert len(boards[0]["columns"]) == 6

    column_statuses = [c["ticket_status"] for c in boards[0]["columns"]]
    assert "backlog" in column_statuses
    assert "done" in column_statuses


async def test_project_isolation_between_users(
    auth_client: AsyncClient,
    second_user: User,
    project: Project,
):
    """A user should not see another user's projects."""
    from src.auth import create_access_token
    from httpx import ASGITransport, AsyncClient as AC
    from src.main import app

    token = create_access_token(second_user.id)
    transport = ASGITransport(app=app)
    async with AC(transport=transport, base_url="http://test") as client2:
        client2.headers["Authorization"] = f"Bearer {token}"
        resp = await client2.get("/api/projects")
        assert resp.status_code == 200
        assert resp.json() == []

        # Should not access other user's project
        resp = await client2.get(f"/api/projects/{project.id}")
        assert resp.status_code == 404
