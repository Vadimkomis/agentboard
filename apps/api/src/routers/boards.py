import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth import get_current_user
from src.database import get_db
from src.models.board import Board, BoardColumn
from src.models.project import Project
from src.models.user import User
from src.schemas.board import BoardResponse

router = APIRouter(prefix="/projects/{project_id}/boards", tags=["boards"])


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


@router.get("", response_model=list[BoardResponse])
async def list_boards(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Board)
        .where(Board.project_id == project_id)
        .options(selectinload(Board.columns))
    )
    return result.scalars().all()


@router.get("/{board_id}", response_model=BoardResponse)
async def get_board(
    project_id: uuid.UUID,
    board_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_project_access(project_id, current_user, db)

    result = await db.execute(
        select(Board)
        .where(Board.id == board_id, Board.project_id == project_id)
        .options(selectinload(Board.columns))
    )
    board = result.scalar_one_or_none()
    if not board:
        raise HTTPException(status_code=404, detail="Board not found")
    return board
