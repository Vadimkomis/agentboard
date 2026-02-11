import uuid
from datetime import datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.board import BoardColumn
from src.models.project import Project
from src.models.ticket import Ticket
from src.models.user import User


async def test_dashboard_stats_empty(auth_client: AsyncClient):
    resp = await auth_client.get("/api/dashboard/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_count"] == 0
    assert data["open_ticket_count"] == 0
    assert data["pr_count"] == 0


async def test_dashboard_stats_with_project(
    auth_client: AsyncClient,
    project: Project,
):
    resp = await auth_client.get("/api/dashboard/stats")
    data = resp.json()
    assert data["project_count"] == 1
    assert data["open_ticket_count"] == 0
    assert data["pr_count"] == 0


async def test_dashboard_stats_with_tickets(
    auth_client: AsyncClient,
    project: Project,
    ticket: Ticket,
):
    resp = await auth_client.get("/api/dashboard/stats")
    data = resp.json()
    assert data["project_count"] == 1
    assert data["open_ticket_count"] == 1  # backlog is not done/cancelled
    assert data["pr_count"] == 0


async def test_dashboard_stats_with_pr(
    auth_client: AsyncClient,
    project: Project,
    user: User,
    backlog_column: BoardColumn,
    override_db: AsyncSession,
):
    """Tickets with PR URLs should count in pr_count."""
    db = override_db
    t = Ticket(
        id=uuid.uuid4(),
        project_id=project.id,
        created_by_id=user.id,
        column_id=backlog_column.id,
        title="PR Ticket",
        position=1,
        status="in_review",
        pr_url="https://github.com/user/repo/pull/1",
        pr_number=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(t)
    await db.commit()

    resp = await auth_client.get("/api/dashboard/stats")
    data = resp.json()
    assert data["pr_count"] == 1
    assert data["open_ticket_count"] == 1


async def test_dashboard_excludes_done_tickets(
    auth_client: AsyncClient,
    project: Project,
    user: User,
    done_column: BoardColumn,
    override_db: AsyncSession,
):
    """Done tickets should not count as open."""
    db = override_db
    t = Ticket(
        id=uuid.uuid4(),
        project_id=project.id,
        created_by_id=user.id,
        column_id=done_column.id,
        title="Done Ticket",
        position=1,
        status="done",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(t)
    await db.commit()

    resp = await auth_client.get("/api/dashboard/stats")
    data = resp.json()
    assert data["open_ticket_count"] == 0
