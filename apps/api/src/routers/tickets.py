import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth import get_current_user
from src.database import get_db
from src.models.board import Board, BoardColumn
from src.models.execution import Execution
from src.models.project import Project
from src.models.ticket import Ticket
from src.models.user import User
from src.schemas.ticket import (
    TicketCreate,
    TicketMoveRequest,
    TicketResponse,
    TicketTransitionRequest,
    TicketUpdate,
)
from src.services.event_bus import publish_event

router = APIRouter(prefix="/projects/{project_id}/tickets", tags=["tickets"])


async def _verify_project_access(
    project_id: uuid.UUID, current_user: User, db: AsyncSession
) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == current_user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("", response_model=list[TicketResponse])
async def list_tickets(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Ticket)
        .where(Ticket.project_id == project_id)
        .order_by(Ticket.position)
    )
    return result.scalars().all()


@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    project_id: uuid.UUID,
    data: TicketCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_project_access(project_id, current_user, db)

    col_result = await db.execute(select(BoardColumn).where(BoardColumn.id == data.column_id))
    column = col_result.scalar_one_or_none()
    if not column:
        raise HTTPException(status_code=400, detail="Invalid column")

    pos_result = await db.execute(
        select(Ticket.position)
        .where(Ticket.column_id == data.column_id)
        .order_by(Ticket.position.desc())
        .limit(1)
    )
    max_pos = pos_result.scalar_one_or_none()
    next_pos = (max_pos or 0) + 1

    ticket = Ticket(
        project_id=project_id,
        created_by_id=current_user.id,
        column_id=data.column_id,
        title=data.title,
        description=data.description,
        position=next_pos,
        status=column.ticket_status,
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)

    # Publish SSE event
    await publish_event(
        f"project:{project_id}",
        "ticket_created",
        {"ticket_id": str(ticket.id), "column_id": str(ticket.column_id), "title": ticket.title},
    )

    # Auto-start planning if user has API key
    if current_user.encrypted_anthropic_key:
        ticket.status = "planning"
        await db.commit()
        try:
            from arq import create_pool
            from arq.connections import RedisSettings

            from src.config import settings

            redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
            await redis.enqueue_job("start_planning_task", str(ticket.id))
        except Exception:
            # If Arq is not available, stay in backlog
            ticket.status = "backlog"
            await db.commit()

    return ticket


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    project_id: uuid.UUID,
    ticket_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.project_id == project_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.patch("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    project_id: uuid.UUID,
    ticket_id: uuid.UUID,
    data: TicketUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.project_id == project_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(ticket, field, value)

    await db.commit()
    await db.refresh(ticket)

    await publish_event(
        f"project:{project_id}",
        "ticket_updated",
        {"ticket_id": str(ticket.id), "status": ticket.status},
    )

    return ticket


@router.post("/{ticket_id}/move", response_model=TicketResponse)
async def move_ticket(
    project_id: uuid.UUID,
    ticket_id: uuid.UUID,
    data: TicketMoveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.project_id == project_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    col_result = await db.execute(select(BoardColumn).where(BoardColumn.id == data.column_id))
    column = col_result.scalar_one_or_none()
    if not column:
        raise HTTPException(status_code=400, detail="Invalid column")

    ticket.column_id = data.column_id
    ticket.position = data.position
    ticket.status = column.ticket_status

    await db.commit()
    await db.refresh(ticket)

    await publish_event(
        f"project:{project_id}",
        "ticket_moved",
        {
            "ticket_id": str(ticket.id),
            "column_id": str(data.column_id),
            "position": data.position,
            "status": ticket.status,
        },
    )

    return ticket


@router.post("/{ticket_id}/transition", response_model=TicketResponse)
async def transition_ticket(
    project_id: uuid.UUID,
    ticket_id: uuid.UUID,
    data: TicketTransitionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Transition a ticket to a new status, moving it to the matching column if one exists."""
    await _verify_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.project_id == project_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Load the board with columns for this project
    board_result = await db.execute(
        select(Board)
        .where(Board.project_id == project_id)
        .options(selectinload(Board.columns))
    )
    board = board_result.scalar_one_or_none()

    # Find column matching the target status
    matching_column = None
    if board:
        matching_column = next(
            (c for c in board.columns if c.ticket_status == data.status), None
        )

    ticket.status = data.status

    if matching_column:
        # Move ticket to the matching column at the end
        pos_result = await db.execute(
            select(func.coalesce(func.max(Ticket.position), 0))
            .where(Ticket.column_id == matching_column.id)
        )
        max_pos = pos_result.scalar_one()
        ticket.column_id = matching_column.id
        ticket.position = max_pos + 1

    await db.commit()
    await db.refresh(ticket)

    if matching_column:
        await publish_event(
            f"project:{project_id}",
            "ticket_moved",
            {
                "ticket_id": str(ticket.id),
                "column_id": str(matching_column.id),
                "position": ticket.position,
                "status": ticket.status,
            },
        )
    else:
        await publish_event(
            f"project:{project_id}",
            "ticket_updated",
            {"ticket_id": str(ticket.id), "status": ticket.status},
        )

    return ticket


@router.post("/{ticket_id}/approve", response_model=TicketResponse)
async def approve_ticket(
    project_id: uuid.UUID,
    ticket_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approve a triaged ticket and start agent execution."""
    await _verify_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.project_id == project_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.status != "ready":
        raise HTTPException(status_code=400, detail="Ticket must be in 'ready' status to approve")

    # Create execution
    execution = Execution(
        ticket_id=ticket.id,
        agent_type=ticket.agent_type or "fullstack",
        runtime=ticket.runtime or "claude",
        branch_name=ticket.branch_name,
    )
    db.add(execution)
    ticket.status = "in_progress"
    await db.commit()
    await db.refresh(execution)

    # Enqueue agent execution
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        from src.config import settings

        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        await redis.enqueue_job("execute_agent_task", str(execution.id))
    except Exception:
        pass

    await publish_event(
        f"project:{project_id}",
        "ticket_approved",
        {"ticket_id": str(ticket.id), "execution_id": str(execution.id)},
    )

    return ticket


@router.post("/{ticket_id}/cancel", response_model=TicketResponse)
async def cancel_ticket(
    project_id: uuid.UUID,
    ticket_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a ticket."""
    await _verify_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.project_id == project_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.status = "cancelled"
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ticket(
    project_id: uuid.UUID,
    ticket_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.project_id == project_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    await db.delete(ticket)
    await db.commit()
