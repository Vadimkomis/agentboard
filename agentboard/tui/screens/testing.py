"""Testing screen — bug report chat panel for stories in TESTING status."""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static

from agentboard.core.db import get_session
from agentboard.core.models import (
    AgentType,
    Runtime,
    Story,
    StoryStatus,
    Ticket,
    TicketStatus,
)
from agentboard.tui.widgets.chat_panel import ChatPanel
from agentboard.tui.widgets.ticket_grid import TicketGrid


class TestingScreen(Screen):
    """Bug report interface for stories in TESTING.

    Lets user describe bugs via chat with PM agent.
    PM creates a bug ticket → story flips back to ENGINEERING.
    """

    TITLE = "Testing"
    BINDINGS = [
        Binding("q,escape", "go_back", "Back"),
        Binding("d", "mark_done", "Mark Done"),
    ]

    DEFAULT_CSS = """
    TestingScreen {
        layout: vertical;
    }
    TestingScreen .main-row {
        height: 1fr;
        layout: horizontal;
    }
    TestingScreen .left-panel {
        width: 50%;
        height: 100%;
        padding: 1;
        border-right: solid $surface-lighten-1;
        layout: vertical;
    }
    TestingScreen .right-panel {
        width: 50%;
        height: 100%;
    }
    TestingScreen .status-info {
        height: auto;
        padding: 1;
        background: $surface-darken-1;
        margin-bottom: 1;
    }
    TestingScreen .action-bar {
        height: 3;
        layout: horizontal;
        align: center middle;
        background: $surface-darken-1;
        padding: 0 1;
    }
    """

    def __init__(self, story: Story, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._story = story
        self._bug_chat: ChatPanel | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(classes="main-row"):
            with Vertical(classes="left-panel"):
                yield Static(
                    f"Testing: {self._story.title}",
                    classes="status-info",
                )
                yield Label("Found a bug? Describe it below and the PM will create a fix ticket.")
                yield ChatPanel(
                    agent_name="Bug Report (PM Agent)",
                    placeholder="Describe the bug — steps to reproduce, expected vs actual...",
                    id="bug-chat",
                )

            with Vertical(classes="right-panel"):
                yield TicketGrid(id="ticket-grid")

        with Horizontal(classes="action-bar"):
            yield Button("[d] Mark Story Done — no more bugs", id="btn-done", variant="success")
            yield Button("Back", id="btn-back", variant="default")

        yield Footer()

    async def on_mount(self) -> None:
        self._bug_chat = self.query_one("#bug-chat", ChatPanel)
        self._bug_chat.set_send_handler(self._on_bug_report)

        # Load tickets
        ticket_grid = self.query_one("#ticket-grid", TicketGrid)
        async with get_session() as session:
            await session.refresh(self._story, ["tickets"])
        ticket_grid.load_tickets(self._story.tickets)

        self._bug_chat.add_message(
            "assistant",
            f"Testing '{self._story.title}'. Found a bug? Describe it here — "
            "I'll create a fix ticket and route it to the right agent.",
        )

    def _on_bug_report(self, text: str) -> None:
        asyncio.create_task(self._handle_bug_report(text))

    async def _handle_bug_report(self, bug_description: str) -> None:
        if not self._bug_chat:
            return

        self._bug_chat.start_streaming()

        try:
            pm_agent = self.app.pm_agent  # type: ignore[attr-defined]
            ticket_data = await pm_agent.triage_bug(self._story, bug_description)

            # Create bug ticket in DB
            async with get_session() as session:
                bug_ticket = Ticket(
                    story_id=self._story.id,
                    ticket_index=self._story.ticket_total,
                    title=ticket_data.get("title", f"Fix: {bug_description[:50]}"),
                    description=ticket_data.get("refined_description", bug_description),
                    acceptance_criteria=ticket_data.get("acceptance_criteria"),
                    prd_anchor=ticket_data.get("prd_anchor"),
                    agent_type=AgentType(ticket_data.get("agent_type", "fullstack")),
                    runtime=Runtime(ticket_data.get("runtime", "claude")),
                    priority=ticket_data.get("priority", "high"),
                    complexity=ticket_data.get("complexity", "low"),
                    branch_name=ticket_data.get("branch_name"),
                    is_bug=True,
                    bug_description=bug_description,
                    status=TicketStatus.pending,
                )
                session.add(bug_ticket)

                # Flip story back to ENGINEERING
                db_story = await session.get(Story, self._story.id)
                if db_story:
                    db_story.status = StoryStatus.engineering
                    self._story = db_story

            # Start execution of bug ticket
            orchestrator = self.app.orchestrator  # type: ignore[attr-defined]
            asyncio.create_task(orchestrator._execute_ticket(self._story.id, bug_ticket))

            self._bug_chat.finish_streaming()
            self._bug_chat.add_message(
                "assistant",
                f"Created bug fix ticket: **{ticket_data.get('title', 'Fix ticket')}**\n\n"
                f"Story is back in ENGINEERING. I'll notify you when the fix is ready for re-testing.",
            )

            # Refresh ticket grid
            ticket_grid = self.query_one("#ticket-grid", TicketGrid)
            async with get_session() as session:
                await session.refresh(self._story, ["tickets"])
            ticket_grid.load_tickets(self._story.tickets)

        except Exception as e:
            self._bug_chat.finish_streaming()
            self._bug_chat.add_message("assistant", f"Failed to create bug ticket: {e}")

    def action_mark_done(self) -> None:
        asyncio.create_task(self._do_mark_done())

    async def _do_mark_done(self) -> None:
        async with get_session() as session:
            db_story = await session.get(Story, self._story.id)
            if db_story:
                db_story.status = StoryStatus.done
        self.notify("Story shipped! Moving to DONE.", title="Done")
        self.action_go_back()

    def action_go_back(self) -> None:
        self.app.pop_screen()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-done":
            self.action_mark_done()
        elif event.button.id == "btn-back":
            self.action_go_back()
