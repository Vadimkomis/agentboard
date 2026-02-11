import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth import get_current_user
from src.database import get_db
from src.models.execution import Execution, ExecutionLog
from src.models.project import Project
from src.models.ticket import Ticket
from src.models.user import User
from src.schemas.execution import ExecutionLogResponse, ExecutionResponse

router = APIRouter(prefix="/projects/{project_id}/tickets/{ticket_id}/executions", tags=["executions"])


async def _verify_ticket_access(
    project_id: uuid.UUID, ticket_id: uuid.UUID, current_user: User, db: AsyncSession
) -> Ticket:
    proj_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == current_user.id)
    )
    if not proj_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Project not found")

    result = await db.execute(
        select(Ticket).where(Ticket.id == ticket_id, Ticket.project_id == project_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.get("", response_model=list[ExecutionResponse])
async def list_executions(
    project_id: uuid.UUID,
    ticket_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_ticket_access(project_id, ticket_id, current_user, db)

    result = await db.execute(
        select(Execution)
        .where(Execution.ticket_id == ticket_id)
        .order_by(Execution.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    project_id: uuid.UUID,
    ticket_id: uuid.UUID,
    execution_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_ticket_access(project_id, ticket_id, current_user, db)

    result = await db.execute(
        select(Execution).where(Execution.id == execution_id, Execution.ticket_id == ticket_id)
    )
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@router.get("/{execution_id}/logs", response_model=list[ExecutionLogResponse])
async def get_execution_logs(
    project_id: uuid.UUID,
    ticket_id: uuid.UUID,
    execution_id: uuid.UUID,
    after_sequence: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_ticket_access(project_id, ticket_id, current_user, db)

    result = await db.execute(
        select(ExecutionLog)
        .where(
            ExecutionLog.execution_id == execution_id,
            ExecutionLog.sequence > after_sequence,
        )
        .order_by(ExecutionLog.sequence)
    )
    return result.scalars().all()
