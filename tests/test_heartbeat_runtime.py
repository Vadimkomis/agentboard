"""Runtime tests for heartbeat scheduling, state loading, and notifications."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agentboard.core import db
from agentboard.core.models import AgentType, Runtime, Story, StoryStatus, Ticket, TicketStatus
from agentboard.workers.heartbeat import HeartbeatMonitor, _desktop_notify, _hours_running


@pytest.fixture
async def heartbeat_database(tmp_path):
    await db.close_db()
    db._session_factory = None
    await db.init_db(tmp_path / "heartbeat.db")
    yield
    await db.close_db()
    db._session_factory = None


async def test_start_stop_and_cancelled_loop():
    monitor = HeartbeatMonitor(interval_minutes=10)
    with patch.object(monitor, "_loop", AsyncMock()) as loop:
        await monitor.start()
        await asyncio.sleep(0)
        await monitor.stop()
        loop.assert_awaited_once()
        assert monitor._running is False


async def test_check_now_updates_status():
    monitor = HeartbeatMonitor()
    monitor._load_board_state = AsyncMock(return_value={"stories": []})
    monitor._invoke_claude = AsyncMock(return_value="HEARTBEAT_OK")

    assert await monitor.check_now() == "HEARTBEAT_OK"
    assert monitor.last_status == "HEARTBEAT_OK"
    assert monitor.last_check is not None


async def test_loop_alerts_and_recovers_from_error():
    monitor = HeartbeatMonitor(interval_minutes=0)
    monitor._running = True
    monitor.check_now = AsyncMock(
        side_effect=["Needs attention", RuntimeError("temporary"), asyncio.CancelledError()]
    )
    monitor._alert = AsyncMock()
    with pytest.raises(asyncio.CancelledError):
        await monitor._loop()
    monitor._alert.assert_awaited_once_with("Needs attention")


async def test_load_board_state_skips_done_and_describes_active(heartbeat_database):
    async with db.get_session() as session:
        active = Story(
            title="Active",
            status=StoryStatus.engineering,
            prd_gtm="Plan",
            last_activity_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2),
        )
        done = Story(title="Done", status=StoryStatus.done)
        session.add_all([active, done])
        await session.flush()
        session.add(
            Ticket(
                story_id=active.id,
                title="Slow task",
                agent_type=AgentType.backend,
                runtime=Runtime.claude,
                status=TicketStatus.in_progress,
                started_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=4),
                is_stale=True,
            )
        )

    state = await HeartbeatMonitor()._load_board_state()

    assert len(state["stories"]) == 1
    item = state["stories"][0]
    assert item["title"] == "Active"
    assert item["hours_inactive"] >= 1.9
    assert item["stuck_tickets"][0]["title"] == "Slow task"
    assert item["stale_tickets"] == [{"id": 1, "title": "Slow task"}]


class _Process:
    def __init__(self, output=b"HEARTBEAT_OK", *, wait_error=None):
        self.output = output
        self.wait_error = wait_error

    async def communicate(self):
        return self.output, b""

    async def wait(self):
        if self.wait_error:
            raise self.wait_error
        return 0


async def test_invoke_claude_success_timeout_and_fallback():
    monitor = HeartbeatMonitor()
    state = {"stories": []}

    async def time_out(awaitable, *, timeout):
        awaitable.close()
        raise TimeoutError

    with patch(
        "agentboard.workers.heartbeat.asyncio.create_subprocess_exec",
        AsyncMock(return_value=_Process(b"  HEARTBEAT_OK\n")),
    ):
        assert await monitor._invoke_claude(state) == "HEARTBEAT_OK"

    with (
        patch(
            "agentboard.workers.heartbeat.asyncio.create_subprocess_exec",
            AsyncMock(return_value=_Process()),
        ),
        patch("agentboard.workers.heartbeat.asyncio.wait_for", side_effect=time_out),
    ):
        assert await monitor._invoke_claude(state) == "HEARTBEAT_OK"

    with patch(
        "agentboard.workers.heartbeat.asyncio.create_subprocess_exec",
        AsyncMock(side_effect=OSError("missing")),
    ):
        assert "Pipeline is empty" in await monitor._invoke_claude(state)


async def test_alert_callback_and_desktop_notification():
    callback = Mock()
    monitor = HeartbeatMonitor(on_alert=callback)
    with patch("agentboard.workers.heartbeat._desktop_notify", AsyncMock()) as desktop:
        await monitor._alert("Warning")
    callback.assert_called_once_with("Warning")
    desktop.assert_awaited_once_with("AgentBoard", "Warning")


@pytest.mark.parametrize(
    ("system", "expected_command"),
    [("Darwin", "osascript"), ("Linux", "notify-send")],
)
async def test_desktop_notify_supported_platforms(system, expected_command):
    process = _Process()
    create = AsyncMock(return_value=process)
    with (
        patch("agentboard.workers.heartbeat.platform.system", return_value=system),
        patch("agentboard.workers.heartbeat.asyncio.create_subprocess_exec", create),
    ):
        await _desktop_notify("Title", "Message")
    assert create.await_args.args[0] == expected_command


async def test_desktop_notify_ignores_unsupported_and_errors():
    create = AsyncMock(side_effect=OSError("no notifier"))
    with (
        patch("agentboard.workers.heartbeat.platform.system", return_value="Windows"),
        patch("agentboard.workers.heartbeat.asyncio.create_subprocess_exec", create),
    ):
        await _desktop_notify("Title", "Message")
    create.assert_not_awaited()

    with (
        patch("agentboard.workers.heartbeat.platform.system", return_value="Linux"),
        patch("agentboard.workers.heartbeat.asyncio.create_subprocess_exec", create),
    ):
        await _desktop_notify("Title", "Message")


def test_hours_running_handles_missing_naive_and_aware_timestamps():
    assert _hours_running(SimpleNamespace(started_at=None)) == 0
    naive = SimpleNamespace(started_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2))
    aware = SimpleNamespace(started_at=datetime.now(UTC) - timedelta(hours=1))
    assert 1.9 < _hours_running(naive) < 2.1
    assert 0.9 < _hours_running(aware) < 1.1
