"""Arq worker tasks — triage and agent execution."""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.database import async_session
from src.models.execution import Execution
from src.models.notification import Notification
from src.models.planning_message import PlanningMessage
from src.models.project import Project
from src.models.ticket import Ticket
from src.models.user import User
from src.services.encryption import decrypt_key
from src.services.event_bus import publish_event
from src.services.pm_agent import generate_planning_reply, triage_ticket

logger = structlog.get_logger()


async def triage_ticket_task(ctx: dict, ticket_id: str) -> None:
    """Fetch ticket, run PM agent triage, update ticket with results."""
    async with async_session() as db:
        result = await db.execute(select(Ticket).where(Ticket.id == uuid.UUID(ticket_id)))
        ticket = result.scalar_one_or_none()
        if not ticket:
            logger.warning("triage_ticket_not_found", ticket_id=ticket_id)
            return

        proj_result = await db.execute(select(Project).where(Project.id == ticket.project_id))
        project = proj_result.scalar_one_or_none()
        if not project:
            return

        # Get the ticket creator's Anthropic key
        user_result = await db.execute(select(User).where(User.id == ticket.created_by_id))
        user = user_result.scalar_one_or_none()
        if not user or not user.encrypted_anthropic_key:
            logger.warning("triage_no_api_key", ticket_id=ticket_id)
            ticket.status = "backlog"
            await db.commit()
            return

        try:
            anthropic_key = decrypt_key(user.encrypted_anthropic_key)
            triage_result = await triage_ticket(ticket, project, anthropic_key)

            ticket.agent_type = triage_result.agent_type
            ticket.runtime = triage_result.runtime
            ticket.priority = triage_result.priority
            ticket.complexity = triage_result.complexity
            ticket.branch_name = triage_result.branch_name
            ticket.refined_description = triage_result.refined_description
            ticket.acceptance_criteria = triage_result.acceptance_criteria
            ticket.context_files = triage_result.context_files
            ticket.triage_reasoning = triage_result.reasoning
            ticket.status = "ready"
            await db.commit()

            # Notify user
            notification = Notification(
                user_id=user.id,
                ticket_id=ticket.id,
                type="triaged",
                title=f"Ticket triaged: {ticket.title}",
                body=f"Agent: {triage_result.agent_type}, Runtime: {triage_result.runtime}, "
                f"Priority: {triage_result.priority}",
            )
            db.add(notification)
            await db.commit()

            await publish_event(
                f"project:{project.id}",
                "triage_complete",
                {
                    "ticket_id": ticket_id,
                    "agent_type": triage_result.agent_type,
                    "runtime": triage_result.runtime,
                    "priority": triage_result.priority,
                    "status": "ready",
                },
            )

        except Exception as e:
            logger.error("triage_failed", ticket_id=ticket_id, error=str(e))
            ticket.status = "backlog"
            await db.commit()


async def execute_agent_task(ctx: dict, execution_id: str) -> None:
    """Run the assigned agent (Claude or Codex) for an execution."""
    async with async_session() as db:
        result = await db.execute(
            select(Execution).where(Execution.id == uuid.UUID(execution_id))
        )
        execution = result.scalar_one_or_none()
        if not execution:
            return

        ticket_result = await db.execute(
            select(Ticket).where(Ticket.id == execution.ticket_id)
        )
        ticket = ticket_result.scalar_one_or_none()
        if not ticket:
            return

        proj_result = await db.execute(select(Project).where(Project.id == ticket.project_id))
        project = proj_result.scalar_one_or_none()
        if not project:
            return

        user_result = await db.execute(select(User).where(User.id == project.owner_id))
        user = user_result.scalar_one_or_none()
        if not user:
            return

        try:
            if execution.runtime == "claude":
                if not user.encrypted_anthropic_key:
                    raise ValueError("Anthropic API key not configured")
                anthropic_key = decrypt_key(user.encrypted_anthropic_key)
                from src.services.claude_runner import run_claude_agent

                await run_claude_agent(
                    execution, ticket, project, anthropic_key, "", db
                )
            elif execution.runtime == "codex":
                if not user.encrypted_openai_key:
                    raise ValueError("OpenAI API key not configured")
                openai_key = decrypt_key(user.encrypted_openai_key)
                from src.services.codex_runner import run_codex_agent

                await run_codex_agent(
                    execution, ticket, project, openai_key, "", db
                )

            # Create notification
            notification = Notification(
                user_id=user.id,
                ticket_id=ticket.id,
                type="pr_created" if ticket.pr_url else "execution_started",
                title=f"Agent completed: {ticket.title}",
                body=f"PR: {ticket.pr_url}" if ticket.pr_url else "Execution finished",
            )
            db.add(notification)
            await db.commit()

        except Exception as e:
            logger.error("execute_agent_failed", execution_id=execution_id, error=str(e))
            execution.status = "failed"
            execution.error_message = str(e)
            await db.commit()


async def _run_planning_reply(
    db: AsyncSession, ticket: Ticket, project: Project, user: User
) -> None:
    """Shared logic for generating a PM planning reply with streaming."""
    anthropic_key = decrypt_key(user.encrypted_anthropic_key)

    # Load conversation history
    msgs_result = await db.execute(
        select(PlanningMessage)
        .where(PlanningMessage.ticket_id == ticket.id)
        .order_by(PlanningMessage.sequence)
    )
    messages = msgs_result.scalars().all()
    conversation_history = [
        {"role": msg.role, "content": msg.content} for msg in messages
    ]

    # If no messages yet, add an initial user message with the ticket info
    if not conversation_history:
        conversation_history = [
            {
                "role": "user",
                "content": (
                    f"I just created a ticket:\n\n"
                    f"**{ticket.title}**\n\n"
                    f"{ticket.description or 'No description provided'}\n\n"
                    f"Please analyze this and help me plan the implementation."
                ),
            }
        ]

    # Get next sequence number
    max_seq = max((m.sequence for m in messages), default=0)
    next_seq = max_seq + 1

    # Create streaming assistant message
    assistant_msg = PlanningMessage(
        ticket_id=ticket.id,
        sequence=next_seq,
        role="assistant",
        content="",
        is_streaming=True,
    )
    db.add(assistant_msg)
    await db.commit()
    await db.refresh(assistant_msg)

    await publish_event(
        f"project:{ticket.project_id}",
        "planning_message_new",
        {
            "ticket_id": str(ticket.id),
            "message_id": str(assistant_msg.id),
            "sequence": assistant_msg.sequence,
            "role": "assistant",
            "is_streaming": True,
        },
    )

    async def on_token(token: str) -> None:
        await publish_event(
            f"project:{ticket.project_id}",
            "planning_message_delta",
            {
                "ticket_id": str(ticket.id),
                "message_id": str(assistant_msg.id),
                "content_delta": token,
            },
        )

    try:
        full_text = await generate_planning_reply(
            ticket, project, conversation_history, anthropic_key, on_token
        )
        assistant_msg.content = full_text
        assistant_msg.is_streaming = False
        await db.commit()
    except Exception as e:
        logger.error(
            "planning_reply_failed", ticket_id=str(ticket.id), error=str(e)
        )
        assistant_msg.content = (
            assistant_msg.content or "Sorry, an error occurred."
        )
        assistant_msg.is_streaming = False
        await db.commit()

    await publish_event(
        f"project:{ticket.project_id}",
        "planning_message_complete",
        {
            "ticket_id": str(ticket.id),
            "message_id": str(assistant_msg.id),
        },
    )


async def start_planning_task(ctx: dict, ticket_id: str) -> None:
    """Called on ticket creation. PM sends first planning message."""
    async with async_session() as db:
        result = await db.execute(
            select(Ticket).where(Ticket.id == uuid.UUID(ticket_id))
        )
        ticket = result.scalar_one_or_none()
        if not ticket:
            logger.warning("start_planning_ticket_not_found", ticket_id=ticket_id)
            return

        proj_result = await db.execute(
            select(Project).where(Project.id == ticket.project_id)
        )
        project = proj_result.scalar_one_or_none()
        if not project:
            return

        user_result = await db.execute(
            select(User).where(User.id == ticket.created_by_id)
        )
        user = user_result.scalar_one_or_none()
        if not user or not user.encrypted_anthropic_key:
            logger.warning("planning_no_api_key", ticket_id=ticket_id)
            ticket.status = "backlog"
            await db.commit()
            return

        try:
            await _run_planning_reply(db, ticket, project, user)
        except Exception as e:
            logger.error(
                "start_planning_failed", ticket_id=ticket_id, error=str(e)
            )
            ticket.status = "backlog"
            await db.commit()


async def generate_pm_reply_task(
    ctx: dict, ticket_id: str, user_id: str
) -> None:
    """Called when user sends a planning message. PM generates a reply."""
    async with async_session() as db:
        result = await db.execute(
            select(Ticket).where(Ticket.id == uuid.UUID(ticket_id))
        )
        ticket = result.scalar_one_or_none()
        if not ticket:
            return

        proj_result = await db.execute(
            select(Project).where(Project.id == ticket.project_id)
        )
        project = proj_result.scalar_one_or_none()
        if not project:
            return

        user_result = await db.execute(
            select(User).where(User.id == uuid.UUID(user_id))
        )
        user = user_result.scalar_one_or_none()
        if not user or not user.encrypted_anthropic_key:
            return

        try:
            await _run_planning_reply(db, ticket, project, user)
        except Exception as e:
            logger.error(
                "pm_reply_failed", ticket_id=ticket_id, error=str(e)
            )


class WorkerSettings:
    """Arq worker settings."""

    functions = [
        triage_ticket_task,
        execute_agent_task,
        start_planning_task,
        generate_pm_reply_task,
    ]
    redis_settings = settings.redis_url
