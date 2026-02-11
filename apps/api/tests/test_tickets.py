import uuid
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from src.models.board import Board, BoardColumn
from src.models.project import Project
from src.models.ticket import Ticket
from src.models.user import User


async def test_list_tickets_empty(auth_client: AsyncClient, project: Project):
    resp = await auth_client.get(f"/api/projects/{project.id}/tickets")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_ticket(
    auth_client: AsyncClient,
    project: Project,
    backlog_column: BoardColumn,
):
    resp = await auth_client.post(
        f"/api/projects/{project.id}/tickets",
        json={
            "title": "Fix login bug",
            "description": "Users can't log in with GitHub",
            "column_id": str(backlog_column.id),
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Fix login bug"
    assert data["description"] == "Users can't log in with GitHub"
    assert data["status"] == "backlog"
    assert data["column_id"] == str(backlog_column.id)
    assert data["project_id"] == str(project.id)


async def test_create_ticket_invalid_column(
    auth_client: AsyncClient,
    project: Project,
):
    fake_col = uuid.uuid4()
    resp = await auth_client.post(
        f"/api/projects/{project.id}/tickets",
        json={
            "title": "Bad ticket",
            "column_id": str(fake_col),
        },
    )
    assert resp.status_code == 400


async def test_get_ticket(auth_client: AsyncClient, project: Project, ticket: Ticket):
    resp = await auth_client.get(
        f"/api/projects/{project.id}/tickets/{ticket.id}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Test Ticket"
    assert data["id"] == str(ticket.id)


async def test_get_nonexistent_ticket(auth_client: AsyncClient, project: Project):
    fake_id = uuid.uuid4()
    resp = await auth_client.get(f"/api/projects/{project.id}/tickets/{fake_id}")
    assert resp.status_code == 404


async def test_update_ticket(auth_client: AsyncClient, project: Project, ticket: Ticket):
    resp = await auth_client.patch(
        f"/api/projects/{project.id}/tickets/{ticket.id}",
        json={"title": "Updated Title", "priority": "high"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Updated Title"
    assert data["priority"] == "high"


async def test_move_ticket(
    auth_client: AsyncClient,
    project: Project,
    ticket: Ticket,
    ready_column: BoardColumn,
):
    resp = await auth_client.post(
        f"/api/projects/{project.id}/tickets/{ticket.id}/move",
        json={"column_id": str(ready_column.id), "position": 0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["column_id"] == str(ready_column.id)
    assert data["status"] == "ready"
    assert data["position"] == 0


async def test_move_ticket_to_invalid_column(
    auth_client: AsyncClient,
    project: Project,
    ticket: Ticket,
):
    fake_col = uuid.uuid4()
    resp = await auth_client.post(
        f"/api/projects/{project.id}/tickets/{ticket.id}/move",
        json={"column_id": str(fake_col), "position": 0},
    )
    assert resp.status_code == 400


async def test_delete_ticket(auth_client: AsyncClient, project: Project, ticket: Ticket):
    resp = await auth_client.delete(
        f"/api/projects/{project.id}/tickets/{ticket.id}"
    )
    assert resp.status_code == 204

    # Verify it's gone
    resp = await auth_client.get(
        f"/api/projects/{project.id}/tickets/{ticket.id}"
    )
    assert resp.status_code == 404


async def test_approve_ticket_not_ready(
    auth_client: AsyncClient,
    project: Project,
    ticket: Ticket,
):
    """Cannot approve a ticket that's not in 'ready' status."""
    resp = await auth_client.post(
        f"/api/projects/{project.id}/tickets/{ticket.id}/approve"
    )
    assert resp.status_code == 400
    assert "ready" in resp.json()["detail"].lower()


async def test_approve_ticket(
    auth_client: AsyncClient,
    project: Project,
    ticket: Ticket,
    ready_column: BoardColumn,
):
    """Approve a triaged ticket that is in 'ready' status."""
    # First move ticket to ready
    await auth_client.post(
        f"/api/projects/{project.id}/tickets/{ticket.id}/move",
        json={"column_id": str(ready_column.id), "position": 0},
    )

    resp = await auth_client.post(
        f"/api/projects/{project.id}/tickets/{ticket.id}/approve"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "in_progress"


async def test_cancel_ticket(
    auth_client: AsyncClient,
    project: Project,
    ticket: Ticket,
):
    resp = await auth_client.post(
        f"/api/projects/{project.id}/tickets/{ticket.id}/cancel"
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


async def test_ticket_position_auto_increments(
    auth_client: AsyncClient,
    project: Project,
    backlog_column: BoardColumn,
):
    """Multiple tickets in the same column should have incrementing positions."""
    resp1 = await auth_client.post(
        f"/api/projects/{project.id}/tickets",
        json={"title": "Ticket 1", "column_id": str(backlog_column.id)},
    )
    resp2 = await auth_client.post(
        f"/api/projects/{project.id}/tickets",
        json={"title": "Ticket 2", "column_id": str(backlog_column.id)},
    )
    assert resp1.json()["position"] < resp2.json()["position"]


async def test_tickets_in_nonexistent_project(auth_client: AsyncClient):
    fake_id = uuid.uuid4()
    resp = await auth_client.get(f"/api/projects/{fake_id}/tickets")
    assert resp.status_code == 404
