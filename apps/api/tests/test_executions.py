import uuid
from datetime import datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.execution import Execution, ExecutionLog
from src.models.project import Project
from src.models.ticket import Ticket


async def test_list_executions_empty(
    auth_client: AsyncClient,
    project: Project,
    ticket: Ticket,
):
    resp = await auth_client.get(
        f"/api/projects/{project.id}/tickets/{ticket.id}/executions"
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_executions(
    auth_client: AsyncClient,
    project: Project,
    ticket: Ticket,
    override_db: AsyncSession,
):
    db = override_db
    ex = Execution(
        id=uuid.uuid4(),
        ticket_id=ticket.id,
        agent_type="fullstack",
        runtime="claude",
        status="completed",
        total_tokens=1500,
        total_cost=0.05,
        created_at=datetime.utcnow(),
    )
    db.add(ex)
    await db.commit()

    resp = await auth_client.get(
        f"/api/projects/{project.id}/tickets/{ticket.id}/executions"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["agent_type"] == "fullstack"
    assert data[0]["runtime"] == "claude"
    assert data[0]["status"] == "completed"


async def test_get_execution(
    auth_client: AsyncClient,
    project: Project,
    ticket: Ticket,
    override_db: AsyncSession,
):
    db = override_db
    ex = Execution(
        id=uuid.uuid4(),
        ticket_id=ticket.id,
        agent_type="backend",
        runtime="codex",
        status="running",
        created_at=datetime.utcnow(),
    )
    db.add(ex)
    await db.commit()
    await db.refresh(ex)

    resp = await auth_client.get(
        f"/api/projects/{project.id}/tickets/{ticket.id}/executions/{ex.id}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(ex.id)
    assert data["agent_type"] == "backend"


async def test_get_nonexistent_execution(
    auth_client: AsyncClient,
    project: Project,
    ticket: Ticket,
):
    fake_id = uuid.uuid4()
    resp = await auth_client.get(
        f"/api/projects/{project.id}/tickets/{ticket.id}/executions/{fake_id}"
    )
    assert resp.status_code == 404


async def test_get_execution_logs(
    auth_client: AsyncClient,
    project: Project,
    ticket: Ticket,
    override_db: AsyncSession,
):
    db = override_db
    ex = Execution(
        id=uuid.uuid4(),
        ticket_id=ticket.id,
        agent_type="fullstack",
        runtime="claude",
        status="running",
        created_at=datetime.utcnow(),
    )
    db.add(ex)
    await db.flush()

    for i in range(3):
        log = ExecutionLog(
            id=uuid.uuid4(),
            execution_id=ex.id,
            sequence=i + 1,
            log_type="assistant",
            content=f"Log entry {i + 1}",
            created_at=datetime.utcnow(),
        )
        db.add(log)
    await db.commit()

    resp = await auth_client.get(
        f"/api/projects/{project.id}/tickets/{ticket.id}/executions/{ex.id}/logs"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert data[0]["sequence"] == 1
    assert data[2]["sequence"] == 3


async def test_get_execution_logs_after_sequence(
    auth_client: AsyncClient,
    project: Project,
    ticket: Ticket,
    override_db: AsyncSession,
):
    """Test the after_sequence filter for log streaming."""
    db = override_db
    ex = Execution(
        id=uuid.uuid4(),
        ticket_id=ticket.id,
        agent_type="fullstack",
        runtime="claude",
        status="running",
        created_at=datetime.utcnow(),
    )
    db.add(ex)
    await db.flush()

    for i in range(5):
        log = ExecutionLog(
            id=uuid.uuid4(),
            execution_id=ex.id,
            sequence=i + 1,
            log_type="assistant",
            content=f"Entry {i + 1}",
            created_at=datetime.utcnow(),
        )
        db.add(log)
    await db.commit()

    # Get logs after sequence 3
    resp = await auth_client.get(
        f"/api/projects/{project.id}/tickets/{ticket.id}/executions/{ex.id}/logs",
        params={"after_sequence": 3},
    )
    data = resp.json()
    assert len(data) == 2
    assert data[0]["sequence"] == 4
    assert data[1]["sequence"] == 5
