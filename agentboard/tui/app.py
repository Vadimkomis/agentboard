"""AgentBoardApp — Textual root application.

Initializes: DB, config, agents, orchestrator, heartbeat.
Manages screen transitions and global state.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from textual.app import App

from agentboard.core.config import Config, get_config
from agentboard.core.db import close_db, init_db


class AgentBoardApp(App):
    """Root Textual application for AgentBoard."""

    TITLE = "AgentBoard"
    CSS = """
    Screen {
        background: $background;
    }
    """

    def __init__(self, config: Config | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._config = config or get_config()
        self.pm_agent: object | None = None
        self.growth_agent: object | None = None
        self.orchestrator: object | None = None
        self._heartbeat: object | None = None

    async def on_mount(self) -> None:
        """Initialize all services and push the board screen."""
        # Init DB
        await init_db(self._config.db_file)

        # Init LLM clients
        llm_client = self._build_llm_client()

        # Init agents
        from agentboard.agents.engineering_runner import EngineeringRunner
        from agentboard.agents.growth_agent import GrowthAgent
        from agentboard.agents.pm_agent import PMAgent
        from agentboard.workers.heartbeat import HeartbeatMonitor
        from agentboard.workers.orchestrator import Orchestrator

        self.pm_agent = PMAgent(llm_client)
        self.growth_agent = GrowthAgent(llm_client)

        runner = EngineeringRunner(self._config)
        self.orchestrator = Orchestrator(
            engineering_runner=runner,
            on_story_update=self._on_story_status_changed,
            on_ticket_update=self._on_ticket_status_changed,
        )

        # Start heartbeat
        self._heartbeat = HeartbeatMonitor(
            claude_cli_path=self._config.claude_cli_path,
            interval_minutes=self._config.heartbeat_interval_minutes,
            on_alert=self._on_heartbeat_alert,
        )
        await self._heartbeat.start()  # type: ignore[union-attr]

        # Push board screen
        from agentboard.tui.screens.board import BoardScreen

        await self.push_screen(BoardScreen())

    def _build_llm_client(self) -> object:
        """Build the appropriate LLM client based on config."""
        provider = self._config.default_provider
        if provider == "claude":
            try:
                from agentboard.llm.claude_cli import ClaudeCLIClient

                return ClaudeCLIClient(self._config.claude_cli_path)
            except RuntimeError:
                pass

        # Fallback: try codex regardless of provider setting
        try:
            from agentboard.llm.codex_cli import CodexCLIClient

            return CodexCLIClient(self._config.codex_cli_path)
        except RuntimeError:
            pass

        raise RuntimeError(
            "No LLM CLI found. Install claude CLI: npm install -g @anthropic-ai/claude-code\n"
            "Or codex CLI: npm install -g @openai/codex"
        )

    def _on_story_status_changed(self, story_id: int, status: object) -> None:
        """Called by orchestrator when a story changes status."""
        from agentboard.core.models import StoryStatus

        assert isinstance(status, StoryStatus)

        if status == StoryStatus.testing:
            self.notify(
                "Story is ready for testing!",
                title="Testing",
                timeout=10,
            )

        # Refresh board if visible
        from agentboard.tui.screens.board import BoardScreen

        current = self.screen
        if isinstance(current, BoardScreen):
            asyncio.create_task(current.refresh_board())

    def _on_ticket_status_changed(self, ticket_id: int, status: object) -> None:
        """Called by orchestrator when a ticket changes status."""
        pass  # Board screen refreshes on story update

    def _on_heartbeat_alert(self, message: str) -> None:
        """Show heartbeat alert in TUI."""
        from datetime import datetime

        self.notify(message, title="AgentBoard Alert", timeout=30, severity="warning")

        # Update heartbeat bar
        try:
            from agentboard.tui.widgets.heartbeat_bar import HeartbeatBar

            bar = self.query_one(HeartbeatBar)
            bar.update_status(datetime.now(UTC), message)
        except Exception:
            pass

    def trigger_heartbeat(self) -> None:
        """Force an immediate heartbeat check."""

        async def _do_check() -> None:
            if self._heartbeat is None:
                return
            result = await self._heartbeat.check_now()  # type: ignore[union-attr]
            try:
                from agentboard.tui.widgets.heartbeat_bar import HeartbeatBar

                bar = self.query_one(HeartbeatBar)
                bar.update_status(datetime.now(UTC), result)
            except Exception:
                pass
            if result.strip() != "HEARTBEAT_OK":
                self.notify(result, title="Heartbeat Alert", severity="warning")
            else:
                self.notify("All systems healthy", title="Heartbeat OK")

        asyncio.create_task(_do_check())

    async def refresh_story(self, story: object) -> None:
        """Re-fetch story from DB (used by detail screen)."""
        from agentboard.core.db import get_session
        from agentboard.core.models import Story

        assert isinstance(story, Story)
        async with get_session() as session:
            await session.refresh(story, ["tickets", "pm_messages", "growth_messages"])

    async def on_unmount(self) -> None:
        if self._heartbeat:
            await self._heartbeat.stop()  # type: ignore[union-attr]
        await close_db()
