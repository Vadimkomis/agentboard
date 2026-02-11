import uuid
from datetime import datetime

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.notification import Notification
from src.models.user import User


async def _create_notification(
    db: AsyncSession,
    user: User,
    title: str = "Test notification",
    type: str = "triaged",
    read: bool = False,
) -> Notification:
    n = Notification(
        id=uuid.uuid4(),
        user_id=user.id,
        type=type,
        title=title,
        body="Some body text",
        read=read,
        created_at=datetime.utcnow(),
    )
    db.add(n)
    await db.commit()
    await db.refresh(n)
    return n


async def test_list_notifications_empty(auth_client: AsyncClient):
    resp = await auth_client.get("/api/notifications")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_notifications(
    auth_client: AsyncClient,
    user: User,
    override_db: AsyncSession,
):
    await _create_notification(override_db, user, "First")
    await _create_notification(override_db, user, "Second")

    resp = await auth_client.get("/api/notifications")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


async def test_unread_count(
    auth_client: AsyncClient,
    user: User,
    override_db: AsyncSession,
):
    await _create_notification(override_db, user, "Unread 1", read=False)
    await _create_notification(override_db, user, "Unread 2", read=False)
    await _create_notification(override_db, user, "Read 1", read=True)

    resp = await auth_client.get("/api/notifications/unread-count")
    assert resp.status_code == 200
    assert resp.json()["count"] == 2


async def test_mark_notification_read(
    auth_client: AsyncClient,
    user: User,
    override_db: AsyncSession,
):
    notif = await _create_notification(override_db, user, "Mark me read")

    resp = await auth_client.patch(f"/api/notifications/{notif.id}/read")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify unread count decreased
    count_resp = await auth_client.get("/api/notifications/unread-count")
    assert count_resp.json()["count"] == 0


async def test_mark_all_read(
    auth_client: AsyncClient,
    user: User,
    override_db: AsyncSession,
):
    await _create_notification(override_db, user, "Notif 1")
    await _create_notification(override_db, user, "Notif 2")
    await _create_notification(override_db, user, "Notif 3")

    resp = await auth_client.post("/api/notifications/read-all")
    assert resp.status_code == 200

    count_resp = await auth_client.get("/api/notifications/unread-count")
    assert count_resp.json()["count"] == 0


async def test_notification_isolation(
    auth_client: AsyncClient,
    user: User,
    second_user: User,
    override_db: AsyncSession,
):
    """A user should only see their own notifications."""
    await _create_notification(override_db, user, "My notif")
    await _create_notification(override_db, second_user, "Other notif")

    resp = await auth_client.get("/api/notifications")
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "My notif"
