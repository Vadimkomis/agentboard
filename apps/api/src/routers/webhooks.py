import hashlib
import hmac
import json
import uuid

from fastapi import APIRouter, HTTPException, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import async_session
from src.models.notification import Notification
from src.models.project import Project
from src.models.ticket import Ticket
from src.services.event_bus import publish_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _verify_signature(payload: bytes, signature: str | None, secret: str) -> bool:
    if not signature or not secret:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(None),
    x_hub_signature_256: str = Header(None),
):
    """Handle GitHub webhooks (PR merged → ticket done)."""
    body = await request.body()

    # Verify signature if webhook secret is configured
    webhook_secret = getattr(settings, "github_webhook_secret", "")
    if webhook_secret and not _verify_signature(body, x_hub_signature_256, webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body)

    if x_github_event == "pull_request":
        await _handle_pull_request(payload)
    elif x_github_event == "ping":
        return {"status": "pong"}

    return {"status": "ok"}


async def _handle_pull_request(payload: dict) -> None:
    action = payload.get("action")
    pr = payload.get("pull_request", {})

    # Only handle merged PRs
    if action != "closed" or not pr.get("merged"):
        return

    pr_number = pr.get("number")
    repo_full_name = payload.get("repository", {}).get("full_name")
    if not pr_number or not repo_full_name:
        return

    async with async_session() as db:
        # Find the project by repo
        proj_result = await db.execute(
            select(Project).where(Project.repo_full_name == repo_full_name)
        )
        project = proj_result.scalar_one_or_none()
        if not project:
            return

        # Find ticket with this PR number
        ticket_result = await db.execute(
            select(Ticket).where(
                Ticket.project_id == project.id,
                Ticket.pr_number == pr_number,
            )
        )
        ticket = ticket_result.scalar_one_or_none()
        if not ticket:
            return

        # Move ticket to done
        ticket.status = "done"

        # Find "Done" column
        from src.models.board import Board, BoardColumn

        board_result = await db.execute(
            select(Board).where(Board.project_id == project.id).limit(1)
        )
        board = board_result.scalar_one_or_none()
        if board:
            col_result = await db.execute(
                select(BoardColumn).where(
                    BoardColumn.board_id == board.id,
                    BoardColumn.ticket_status == "done",
                )
            )
            done_col = col_result.scalar_one_or_none()
            if done_col:
                ticket.column_id = done_col.id

        # Create notification
        notif = Notification(
            user_id=project.owner_id,
            type="pr_merged",
            title=f"PR #{pr_number} merged",
            message=f"PR for '{ticket.title}' has been merged. Ticket moved to Done.",
            ticket_id=ticket.id,
            project_id=project.id,
        )
        db.add(notif)
        await db.commit()

        # Publish SSE event
        await publish_event(
            f"project:{project.id}",
            "ticket_updated",
            {"ticket_id": str(ticket.id), "status": "done"},
        )
