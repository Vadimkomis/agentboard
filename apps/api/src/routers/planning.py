import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import get_current_user
from src.database import get_db
from src.models.planning_message import PlanningMessage
from src.models.project import Project
from src.models.ticket import Ticket
from src.models.user import User
from src.schemas.planning import PlanningMessageResponse, PlanningUserMessage
from src.services.event_bus import publish_event

router = APIRouter(
    prefix="/projects/{project_id}/tickets/{ticket_id}/planning",
    tags=["planning"],
)


async def _get_ticket_for_planning(
    project_id: uuid.UUID,
    ticket_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> Ticket:
    result = await db.execute(
        select(Project).where(
            Project.id == project_id, Project.owner_id == current_user.id
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(Ticket).where(
            Ticket.id == ticket_id, Ticket.project_id == project_id
        )
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.get("/messages", response_model=list[PlanningMessageResponse])
async def list_planning_messages(
    project_id: uuid.UUID,
    ticket_id: uuid.UUID,
    after_sequence: int | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_ticket_for_planning(project_id, ticket_id, current_user, db)

    query = select(PlanningMessage).where(PlanningMessage.ticket_id == ticket_id)
    if after_sequence is not None:
        query = query.where(PlanningMessage.sequence > after_sequence)
    query = query.order_by(PlanningMessage.sequence)

    result = await db.execute(query)
    return result.scalars().all()


@router.post(
    "/messages",
    response_model=PlanningMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_planning_message(
    project_id: uuid.UUID,
    ticket_id: uuid.UUID,
    data: PlanningUserMessage,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ticket = await _get_ticket_for_planning(
        project_id, ticket_id, current_user, db
    )

    if ticket.status != "planning":
        raise HTTPException(
            status_code=400, detail="Ticket must be in 'planning' status"
        )

    # Check if an assistant message is currently streaming
    streaming_result = await db.execute(
        select(PlanningMessage).where(
            PlanningMessage.ticket_id == ticket_id,
            PlanningMessage.is_streaming.is_(True),
        )
    )
    if streaming_result.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Cannot send a message while the PM is generating a reply",
        )

    # Get next sequence number
    max_seq_result = await db.execute(
        select(func.max(PlanningMessage.sequence)).where(
            PlanningMessage.ticket_id == ticket_id
        )
    )
    max_seq = max_seq_result.scalar_one_or_none() or 0
    next_seq = max_seq + 1

    message = PlanningMessage(
        ticket_id=ticket_id,
        sequence=next_seq,
        role="user",
        content=data.content,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    await publish_event(
        f"project:{project_id}",
        "planning_message_new",
        {
            "ticket_id": str(ticket_id),
            "message_id": str(message.id),
            "sequence": message.sequence,
            "role": "user",
            "is_streaming": False,
        },
    )

    # Enqueue PM reply task
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        from src.config import settings

        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        await redis.enqueue_job(
            "generate_pm_reply_task", str(ticket_id), str(current_user.id)
        )
    except Exception:
        pass

    return message


@router.post("/finalize", response_model=PlanningMessageResponse)
async def finalize_plan(
    project_id: uuid.UUID,
    ticket_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ticket = await _get_ticket_for_planning(
        project_id, ticket_id, current_user, db
    )

    if ticket.status != "planning":
        raise HTTPException(
            status_code=400, detail="Ticket must be in 'planning' status"
        )

    # Ensure at least one assistant message exists
    assistant_result = await db.execute(
        select(PlanningMessage).where(
            PlanningMessage.ticket_id == ticket_id,
            PlanningMessage.role == "assistant",
        )
    )
    if not assistant_result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="At least one PM reply is required before finalizing",
        )

    # Load conversation history
    msgs_result = await db.execute(
        select(PlanningMessage)
        .where(PlanningMessage.ticket_id == ticket_id)
        .order_by(PlanningMessage.sequence)
    )
    messages = msgs_result.scalars().all()

    conversation_history = [
        {"role": msg.role, "content": msg.content} for msg in messages
    ]

    # Get user's API key
    user_result = await db.execute(select(User).where(User.id == current_user.id))
    user = user_result.scalar_one_or_none()
    if not user or not user.encrypted_anthropic_key:
        raise HTTPException(status_code=400, detail="Anthropic API key not configured")

    from src.services.encryption import decrypt_key
    from src.services.pm_agent import finalize_planning

    project_result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = project_result.scalar_one_or_none()

    anthropic_key = decrypt_key(user.encrypted_anthropic_key)
    triage_result = await finalize_planning(
        ticket, project, conversation_history, anthropic_key
    )

    # Apply triage result to ticket
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

    # Add finalization as a message
    max_seq_result = await db.execute(
        select(func.max(PlanningMessage.sequence)).where(
            PlanningMessage.ticket_id == ticket_id
        )
    )
    max_seq = max_seq_result.scalar_one_or_none() or 0

    finalize_msg = PlanningMessage(
        ticket_id=ticket_id,
        sequence=max_seq + 1,
        role="assistant",
        content=f"Plan finalized. Assigned to **{triage_result.agent_type}** agent "
        f"({triage_result.runtime} runtime), "
        f"priority: {triage_result.priority}, complexity: {triage_result.complexity}.",
    )
    db.add(finalize_msg)
    await db.commit()
    await db.refresh(finalize_msg)

    await publish_event(
        f"project:{project_id}",
        "plan_finalized",
        {
            "ticket_id": str(ticket_id),
            "agent_type": triage_result.agent_type,
            "runtime": triage_result.runtime,
            "priority": triage_result.priority,
            "status": "ready",
        },
    )

    return finalize_msg


@router.post("/reopen", response_model=PlanningMessageResponse)
async def reopen_plan(
    project_id: uuid.UUID,
    ticket_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ticket = await _get_ticket_for_planning(
        project_id, ticket_id, current_user, db
    )

    if ticket.status != "ready":
        raise HTTPException(
            status_code=400,
            detail="Ticket must be in 'ready' status to reopen planning",
        )

    ticket.status = "planning"
    await db.commit()

    # Add a system-like message
    max_seq_result = await db.execute(
        select(func.max(PlanningMessage.sequence)).where(
            PlanningMessage.ticket_id == ticket_id
        )
    )
    max_seq = max_seq_result.scalar_one_or_none() or 0

    reopen_msg = PlanningMessage(
        ticket_id=ticket_id,
        sequence=max_seq + 1,
        role="assistant",
        content="Planning reopened. What would you like to change or discuss further?",
    )
    db.add(reopen_msg)
    await db.commit()
    await db.refresh(reopen_msg)

    await publish_event(
        f"project:{project_id}",
        "ticket_updated",
        {"ticket_id": str(ticket_id), "status": "planning"},
    )

    return reopen_msg
