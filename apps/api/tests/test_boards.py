import uuid

from httpx import AsyncClient

from src.models.board import Board
from src.models.project import Project


async def test_list_boards(auth_client: AsyncClient, project: Project):
    resp = await auth_client.get(f"/api/projects/{project.id}/boards")
    assert resp.status_code == 200
    boards = resp.json()
    assert len(boards) == 1
    assert boards[0]["name"] == "Main Board"


async def test_board_has_columns(auth_client: AsyncClient, project: Project):
    resp = await auth_client.get(f"/api/projects/{project.id}/boards")
    boards = resp.json()
    columns = boards[0]["columns"]
    assert len(columns) == 6

    # Verify column ordering
    positions = [c["position"] for c in columns]
    assert positions == sorted(positions)

    # Verify expected statuses
    statuses = {c["ticket_status"] for c in columns}
    expected = {"backlog", "triaging", "ready", "in_progress", "in_review", "done"}
    assert statuses == expected


async def test_get_specific_board(
    auth_client: AsyncClient,
    project: Project,
    board: Board,
):
    resp = await auth_client.get(
        f"/api/projects/{project.id}/boards/{board.id}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(board.id)
    assert data["name"] == "Main Board"
    assert len(data["columns"]) == 6


async def test_get_nonexistent_board(auth_client: AsyncClient, project: Project):
    fake_id = uuid.uuid4()
    resp = await auth_client.get(f"/api/projects/{project.id}/boards/{fake_id}")
    assert resp.status_code == 404


async def test_boards_require_project_access(
    auth_client: AsyncClient,
):
    fake_project = uuid.uuid4()
    resp = await auth_client.get(f"/api/projects/{fake_project}/boards")
    assert resp.status_code == 404
