import json
import uuid
from datetime import datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.board import BoardColumn
from src.models.project import Project
from src.models.ticket import Ticket
from src.models.user import User


async def test_github_webhook_ping(unauth_client: AsyncClient):
    resp = await unauth_client.post(
        "/api/webhooks/github",
        content=json.dumps({}),
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "ping",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pong"


async def test_github_webhook_pr_merged(
    unauth_client: AsyncClient,
    project: Project,
    user: User,
    backlog_column: BoardColumn,
    override_db: AsyncSession,
):
    """When a PR is merged, the associated ticket should move to done."""
    db = override_db
    t = Ticket(
        id=uuid.uuid4(),
        project_id=project.id,
        created_by_id=user.id,
        column_id=backlog_column.id,
        title="PR Ticket",
        position=1,
        status="in_review",
        pr_url="https://github.com/testuser/test-repo/pull/42",
        pr_number=42,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(t)
    await db.commit()

    payload = {
        "action": "closed",
        "pull_request": {
            "number": 42,
            "merged": True,
        },
        "repository": {
            "full_name": "testuser/test-repo",
        },
    }

    resp = await unauth_client.post(
        "/api/webhooks/github",
        content=json.dumps(payload),
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
        },
    )
    assert resp.status_code == 200

    # Verify ticket status changed
    from sqlalchemy import select

    await db.expire_all()
    result = await db.execute(select(Ticket).where(Ticket.id == t.id))
    updated_ticket = result.scalar_one()
    assert updated_ticket.status == "done"


async def test_github_webhook_pr_closed_not_merged(
    unauth_client: AsyncClient,
    project: Project,
    user: User,
    backlog_column: BoardColumn,
    override_db: AsyncSession,
):
    """A closed but not merged PR should NOT change ticket status."""
    db = override_db
    t = Ticket(
        id=uuid.uuid4(),
        project_id=project.id,
        created_by_id=user.id,
        column_id=backlog_column.id,
        title="Closed PR",
        position=1,
        status="in_review",
        pr_number=99,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(t)
    await db.commit()

    payload = {
        "action": "closed",
        "pull_request": {
            "number": 99,
            "merged": False,
        },
        "repository": {
            "full_name": "testuser/test-repo",
        },
    }

    resp = await unauth_client.post(
        "/api/webhooks/github",
        content=json.dumps(payload),
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
        },
    )
    assert resp.status_code == 200

    # Status should be unchanged
    from sqlalchemy import select

    await db.expire_all()
    result = await db.execute(select(Ticket).where(Ticket.id == t.id))
    ticket = result.scalar_one()
    assert ticket.status == "in_review"


async def test_github_webhook_unknown_repo(unauth_client: AsyncClient):
    """Webhook for unknown repo should succeed silently."""
    payload = {
        "action": "closed",
        "pull_request": {
            "number": 1,
            "merged": True,
        },
        "repository": {
            "full_name": "unknown/repo",
        },
    }

    resp = await unauth_client.post(
        "/api/webhooks/github",
        content=json.dumps(payload),
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request",
        },
    )
    assert resp.status_code == 200


async def test_github_webhook_unknown_event(unauth_client: AsyncClient):
    resp = await unauth_client.post(
        "/api/webhooks/github",
        content=json.dumps({"action": "created"}),
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "issues",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
