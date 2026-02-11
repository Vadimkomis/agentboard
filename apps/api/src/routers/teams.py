import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.auth import get_current_user
from src.database import get_db
from src.models.team import Team, TeamMember
from src.models.user import User

router = APIRouter(prefix="/teams", tags=["teams"])


# --- Schemas ---


class TeamCreate(BaseModel):
    name: str
    slug: str


class TeamResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    owner_id: uuid.UUID
    plan_tier: str
    execution_quota: int
    executions_used: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamMemberResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    role: str
    joined_at: datetime

    model_config = {"from_attributes": True}


class InviteMember(BaseModel):
    user_id: uuid.UUID
    role: str = "member"


# --- Endpoints ---


@router.get("", response_model=list[TeamResponse])
async def list_teams(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List teams the current user is a member of."""
    result = await db.execute(
        select(Team)
        .join(TeamMember)
        .where(TeamMember.user_id == current_user.id)
        .order_by(Team.created_at)
    )
    return result.scalars().all()


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    data: TeamCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(Team).where(Team.slug == data.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Slug already taken")

    team = Team(name=data.name, slug=data.slug, owner_id=current_user.id)
    db.add(team)
    await db.flush()

    # Add owner as team member
    member = TeamMember(team_id=team.id, user_id=current_user.id, role="owner")
    db.add(member)
    await db.commit()
    await db.refresh(team)
    return team


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    team = await _get_team_for_user(team_id, current_user.id, db)
    return team


@router.get("/{team_id}/members", response_model=list[TeamMemberResponse])
async def list_members(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_team_for_user(team_id, current_user.id, db)
    result = await db.execute(
        select(TeamMember).where(TeamMember.team_id == team_id)
    )
    return result.scalars().all()


@router.post("/{team_id}/members", response_model=TeamMemberResponse, status_code=201)
async def invite_member(
    team_id: uuid.UUID,
    data: InviteMember,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    team = await _get_team_for_user(team_id, current_user.id, db)

    # Only owner/admin can invite
    caller_member = await _get_membership(team_id, current_user.id, db)
    if caller_member.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    # Check if already a member
    existing = await _get_membership(team_id, data.user_id, db, raise_on_missing=False)
    if existing:
        raise HTTPException(status_code=400, detail="User is already a member")

    member = TeamMember(team_id=team_id, user_id=data.user_id, role=data.role)
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    team = await _get_team_for_user(team_id, current_user.id, db)
    caller_member = await _get_membership(team_id, current_user.id, db)

    if caller_member.role not in ("owner", "admin") and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    if team.owner_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot remove the team owner")

    target = await _get_membership(team_id, user_id, db)
    await db.delete(target)
    await db.commit()


# --- Helpers ---


async def _get_team_for_user(
    team_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> Team:
    result = await db.execute(
        select(Team)
        .join(TeamMember)
        .where(Team.id == team_id, TeamMember.user_id == user_id)
    )
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


async def _get_membership(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
    raise_on_missing: bool = True,
) -> TeamMember | None:
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == user_id
        )
    )
    member = result.scalar_one_or_none()
    if not member and raise_on_missing:
        raise HTTPException(status_code=404, detail="Member not found")
    return member
