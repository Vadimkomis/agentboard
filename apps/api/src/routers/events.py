import uuid

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from src.auth import get_current_user
from src.models.user import User
from src.services.event_bus import subscribe_events

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/projects/{project_id}")
async def project_events(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
):
    """SSE endpoint for real-time project updates (ticket moves, triage, execution logs)."""
    channel = f"project:{project_id}"

    async def event_generator():
        async for message in subscribe_events(channel):
            if message:
                yield {"data": message}
            else:
                yield {"comment": "keepalive"}

    return EventSourceResponse(event_generator())
