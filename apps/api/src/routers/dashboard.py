from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import get_current_user
from src.database import get_db
from src.models.project import Project
from src.models.ticket import Ticket
from src.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_count = (
        await db.execute(
            select(func.count(Project.id)).where(Project.owner_id == current_user.id)
        )
    ).scalar_one()

    # Get all project IDs owned by user
    project_ids_result = await db.execute(
        select(Project.id).where(Project.owner_id == current_user.id)
    )
    project_ids = [r for r in project_ids_result.scalars().all()]

    open_ticket_count = 0
    pr_count = 0
    if project_ids:
        open_ticket_count = (
            await db.execute(
                select(func.count(Ticket.id)).where(
                    Ticket.project_id.in_(project_ids),
                    Ticket.status.notin_(["done", "cancelled"]),
                )
            )
        ).scalar_one()

        pr_count = (
            await db.execute(
                select(func.count(Ticket.id)).where(
                    Ticket.project_id.in_(project_ids),
                    Ticket.pr_url.isnot(None),
                )
            )
        ).scalar_one()

    return {
        "project_count": project_count,
        "open_ticket_count": open_ticket_count,
        "pr_count": pr_count,
    }
