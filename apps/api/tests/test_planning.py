"""Tests for the planning conversation endpoints."""

import uuid
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient

from src.models.planning_message import PlanningMessage
from src.models.project import Project
from src.models.ticket import Ticket
from src.models.user import User


async def test_list_messages_empty(
    auth_client: AsyncClient, project: Project, ticket: Ticket
):
    """Empty conversation returns empty list."""
    resp = await auth_client.get(
        f"/api/projects/{project.id}/tickets/{ticket.id}/planning/messages"
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_messages_returns_existing(
    auth_client: AsyncClient, project: Project, planning_ticket: Ticket
):
    """Listing messages returns existing planning messages."""
    resp = await auth_client.get(
        f"/api/projects/{project.id}/tickets/{planning_ticket.id}/planning/messages"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["role"] == "assistant"
    assert data[0]["sequence"] == 1


async def test_list_messages_after_sequence(
    auth_client: AsyncClient, project: Project, planning_ticket: Ticket
):
    """after_sequence filter returns only newer messages."""
    resp = await auth_client.get(
        f"/api/projects/{project.id}/tickets/{planning_ticket.id}/planning/messages",
        params={"after_sequence": 1},
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_send_message_in_planning_status(
    auth_client: AsyncClient, project: Project, planning_ticket: Ticket
):
    """User can send a message when ticket is in planning status."""
    with patch("src.routers.planning.publish_event", new_callable=AsyncMock):
        resp = await auth_client.post(
            f"/api/projects/{project.id}/tickets/{planning_ticket.id}/planning/messages",
            json={"content": "Can we use Redis for caching?"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["role"] == "user"
    assert data["content"] == "Can we use Redis for caching?"
    assert data["sequence"] == 2
    assert data["is_streaming"] is False


async def test_send_message_rejects_non_planning_status(
    auth_client: AsyncClient, project: Project, ticket: Ticket
):
    """Cannot send message if ticket is not in planning status."""
    resp = await auth_client.post(
        f"/api/projects/{project.id}/tickets/{ticket.id}/planning/messages",
        json={"content": "Hello"},
    )
    assert resp.status_code == 400
    assert "planning" in resp.json()["detail"].lower()


async def test_send_message_rejects_while_streaming(
    auth_client: AsyncClient,
    project: Project,
    planning_ticket: Ticket,
    override_db,
):
    """Cannot send a message while the PM is currently streaming."""
    db = override_db
    streaming_msg = PlanningMessage(
        id=uuid.uuid4(),
        ticket_id=planning_ticket.id,
        sequence=2,
        role="assistant",
        content="",
        is_streaming=True,
    )
    db.add(streaming_msg)
    await db.commit()

    resp = await auth_client.post(
        f"/api/projects/{project.id}/tickets/{planning_ticket.id}/planning/messages",
        json={"content": "Are you done?"},
    )
    assert resp.status_code == 409
    assert "generating" in resp.json()["detail"].lower()


async def test_finalize_plan(
    auth_client: AsyncClient,
    project: Project,
    planning_ticket: Ticket,
    user: User,
    override_db,
):
    """Finalizing plan updates ticket with triage classification."""
    db = override_db
    # Give the user an API key
    user.encrypted_anthropic_key = "encrypted-key"
    await db.commit()

    triage_json = {
        "agent_type": "backend",
        "runtime": "claude",
        "priority": "high",
        "complexity": "medium",
        "branch_name": "feature/plan-this",
        "refined_description": "Refined description from conversation",
        "acceptance_criteria": "- It works",
        "context_files": ["src/main.py"],
        "reasoning": "Based on our discussion",
    }

    with (
        patch("src.routers.planning.decrypt_key", return_value="sk-ant-test"),
        patch(
            "src.routers.planning.finalize_planning",
            new_callable=AsyncMock,
        ) as mock_finalize,
        patch("src.routers.planning.publish_event", new_callable=AsyncMock),
    ):
        from src.schemas.ticket import TriageResult

        mock_finalize.return_value = TriageResult(**triage_json)

        resp = await auth_client.post(
            f"/api/projects/{project.id}/tickets/{planning_ticket.id}/planning/finalize"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "assistant"
    assert "backend" in data["content"]

    # Verify ticket was updated
    await db.refresh(planning_ticket)
    assert planning_ticket.status == "ready"
    assert planning_ticket.agent_type == "backend"
    assert planning_ticket.runtime == "claude"


async def test_finalize_requires_assistant_message(
    auth_client: AsyncClient, project: Project, ticket: Ticket, override_db
):
    """Cannot finalize without at least one assistant message."""
    db = override_db
    ticket.status = "planning"
    await db.commit()

    resp = await auth_client.post(
        f"/api/projects/{project.id}/tickets/{ticket.id}/planning/finalize"
    )
    assert resp.status_code == 400
    assert "reply" in resp.json()["detail"].lower()


async def test_finalize_requires_planning_status(
    auth_client: AsyncClient, project: Project, ticket: Ticket
):
    """Cannot finalize a ticket that's not in planning status."""
    resp = await auth_client.post(
        f"/api/projects/{project.id}/tickets/{ticket.id}/planning/finalize"
    )
    assert resp.status_code == 400
    assert "planning" in resp.json()["detail"].lower()


async def test_reopen_plan(
    auth_client: AsyncClient,
    project: Project,
    ready_ticket: Ticket,
):
    """Reopening a ready ticket moves it back to planning."""
    with patch("src.routers.planning.publish_event", new_callable=AsyncMock):
        resp = await auth_client.post(
            f"/api/projects/{project.id}/tickets/{ready_ticket.id}/planning/reopen"
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "assistant"
    assert "reopened" in data["content"].lower()


async def test_reopen_requires_ready_status(
    auth_client: AsyncClient, project: Project, ticket: Ticket
):
    """Cannot reopen a ticket that's not in ready status."""
    resp = await auth_client.post(
        f"/api/projects/{project.id}/tickets/{ticket.id}/planning/reopen"
    )
    assert resp.status_code == 400
    assert "ready" in resp.json()["detail"].lower()


async def test_planning_messages_nonexistent_ticket(
    auth_client: AsyncClient, project: Project
):
    """Accessing messages for a nonexistent ticket returns 404."""
    fake_id = uuid.uuid4()
    resp = await auth_client.get(
        f"/api/projects/{project.id}/tickets/{fake_id}/planning/messages"
    )
    assert resp.status_code == 404


async def test_planning_messages_nonexistent_project(auth_client: AsyncClient):
    """Accessing messages for a nonexistent project returns 404."""
    fake_project = uuid.uuid4()
    fake_ticket = uuid.uuid4()
    resp = await auth_client.get(
        f"/api/projects/{fake_project}/tickets/{fake_ticket}/planning/messages"
    )
    assert resp.status_code == 404
