"""Heartbeat — asyncio periodic task that monitors pipeline health.

Runs every 30 minutes. Invokes claude CLI with board state to generate alerts.
Silent if everything is healthy (HEARTBEAT_OK).
Sends alerts to TUI notification bar + macOS/Linux desktop notifications.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import platform
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeAlias

from agentboard.core.db import get_session
from agentboard.core.models import Story, StoryStatus, Ticket

logger = logging.getLogger(__name__)

BoardState: TypeAlias = dict[str, Any]

HEARTBEAT_PROMPT = """\
You are a pipeline health monitor for AgentBoard. Analyze the board state and return either:
- "HEARTBEAT_OK" if everything looks healthy
- A concise plain-English alert (1-2 sentences max) if there's an issue

Board state:
{board_state}

Check in this order:
1. Pipeline empty — no stories in DRAFTING or ENGINEERING
2. Stale drafts — story in DRAFTING with no activity for >24h
3. Stuck executions — ticket in_progress for >3h
4. Ready for testing — story just moved to TESTING with no user action
5. Stale tickets — tickets marked is_stale with no action for >1h
6. Missing growth plan — story in ENGINEERING with no LAUNCH.md finalized

Return ONLY "HEARTBEAT_OK" or the alert text. Nothing else.
"""


class HeartbeatMonitor:
    """Periodic health check for the AgentBoard pipeline."""

    def __init__(
        self,
        claude_cli_path: str = "claude",
        interval_minutes: int = 30,
        on_alert: Callable[[str], None] | None = None,
    ) -> None:
        self.claude_cli_path = claude_cli_path
        self.interval_seconds = interval_minutes * 60
        self.on_alert = on_alert
        self.last_check: datetime | None = None
        self.last_status: str = "Not checked yet"
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the heartbeat loop as a background asyncio task."""
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="heartbeat")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def check_now(self) -> str:
        """Run an immediate health check, returning the result."""
        board_state = await self._load_board_state()
        result = await self._invoke_claude(board_state)
        self.last_check = datetime.now(UTC)
        self.last_status = result
        return result

    async def _loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.interval_seconds)
            try:
                result = await self.check_now()
                if result.strip() != "HEARTBEAT_OK":
                    await self._alert(result)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("Heartbeat check failed: %s", e)

    async def _load_board_state(self) -> BoardState:
        """Load current board state from DB for the heartbeat prompt."""
        async with get_session() as session:
            from sqlalchemy import select

            stmt = select(Story)
            result = await session.execute(stmt)
            stories = result.scalars().all()

            now = datetime.now(UTC)
            state: BoardState = {"stories": [], "timestamp": now.isoformat()}

            for story in stories:
                if story.status in (StoryStatus.done,):
                    continue  # Skip archived stories

                await session.refresh(story, ["tickets"])

                last_activity = story.last_activity_at
                # Handle naive datetimes from SQLite
                if last_activity and last_activity.tzinfo is None:
                    last_activity = last_activity.replace(tzinfo=UTC)

                hours_inactive = (
                    (now - last_activity).total_seconds() / 3600 if last_activity else 999
                )

                stuck_tickets = [
                    {"id": t.id, "title": t.title, "hours": _hours_running(t)}
                    for t in story.tickets
                    if t.is_running_too_long
                ]

                stale_tickets = [
                    {"id": t.id, "title": t.title} for t in story.tickets if t.is_stale
                ]

                state["stories"].append(
                    {
                        "id": story.id,
                        "title": story.title,
                        "status": story.status.value,
                        "hours_inactive": round(hours_inactive, 1),
                        "gtm_complete": story.gtm_complete,
                        "launch_md_finalized": story.launch_md_finalized,
                        "ticket_total": story.ticket_total,
                        "ticket_done": story.ticket_done_count,
                        "stuck_tickets": stuck_tickets,
                        "stale_tickets": stale_tickets,
                    }
                )

            return state

    async def _invoke_claude(self, board_state: BoardState) -> str:
        """Invoke claude CLI with board state, returning the response."""
        prompt = HEARTBEAT_PROMPT.format(board_state=json.dumps(board_state, indent=2))
        try:
            proc = await asyncio.create_subprocess_exec(
                self.claude_cli_path,
                "-p",
                prompt,
                "--output-format",
                "text",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
            return stdout.decode().strip()
        except TimeoutError:
            return "HEARTBEAT_OK"  # Don't alert on timeout
        except Exception as e:
            logger.warning("Heartbeat claude invocation failed: %s", e)
            # Fall back to local check without LLM
            return self._local_check(board_state)

    def _local_check(self, board_state: BoardState) -> str:
        """Simple local heuristic check without LLM — used as fallback."""
        stories = board_state.get("stories", [])
        active = [s for s in stories if s["status"] in ("drafting", "refining", "engineering")]

        if not active:
            return "Pipeline is empty — add a story to keep agents working."

        for s in active:
            for stuck in s.get("stuck_tickets", []):
                return (
                    f"Possible stuck agent on '{s['title']}' — "
                    f"ticket '{stuck['title']}' has been running {stuck['hours']:.0f}h"
                )
            if s["hours_inactive"] > 24 and s["status"] in ("drafting", "refining"):
                return (
                    f"'{s['title']}' has been in Drafting for "
                    f"{s['hours_inactive']:.0f}h — ready to finalize?"
                )

        return "HEARTBEAT_OK"

    async def _alert(self, message: str) -> None:
        """Send alert to TUI + optional desktop notification."""
        if self.on_alert and callable(self.on_alert):
            self.on_alert(message)

        # Desktop notification (best-effort)
        await _desktop_notify("AgentBoard", message)


async def _desktop_notify(title: str, message: str) -> None:
    """Send a desktop notification — macOS and Linux."""
    try:
        system = platform.system()
        if system == "Darwin":
            # macOS osascript
            script = f'display notification "{message}" with title "{title}"'
            proc = await asyncio.create_subprocess_exec(
                "osascript",
                "-e",
                script,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=5)
        elif system == "Linux":
            proc = await asyncio.create_subprocess_exec(
                "notify-send",
                title,
                message,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=5)
    except Exception:
        pass  # Desktop notifications are best-effort


def _hours_running(ticket: Ticket) -> float:
    if not ticket.started_at:
        return 0.0
    start = ticket.started_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    return (datetime.now(UTC) - start).total_seconds() / 3600
