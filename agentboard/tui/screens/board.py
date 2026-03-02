"""Kanban board screen — main view with 4 columns: DRAFTING | ENGINEERING | TESTING | DONE."""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from agentboard.core.db import get_session
from agentboard.core.models import Story, StoryStatus
from agentboard.tui.screens.story_detail import DeletePRDConfirmScreen
from agentboard.tui.widgets.story_card import StoryCard

_COLUMNS = [
    (StoryStatus.drafting, StoryStatus.refining),
    (StoryStatus.decomposing, StoryStatus.engineering),
    (StoryStatus.testing,),
    (StoryStatus.done,),
]

_COLUMN_LABELS = ["DRAFTING", "ENGINEERING", "TESTING", "DONE"]


def _can_delete_story(status: StoryStatus) -> bool:
    return status in (StoryStatus.drafting, StoryStatus.refining)


class KanbanColumn(Vertical):
    """A single Kanban column container."""

    DEFAULT_CSS = """
    KanbanColumn {
        width: 1fr;
        height: 100%;
        border-right: solid $surface-lighten-1;
        padding: 0 0;
    }
    KanbanColumn .column-header {
        height: 1;
        background: $primary-darken-2;
        color: $text;
        text-align: center;
        text-style: bold;
        padding: 0 1;
    }
    KanbanColumn .column-body {
        height: 1fr;
        overflow-y: auto;
        padding: 0;
    }
    """

    def __init__(self, label: str, statuses: tuple[StoryStatus, ...], **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._label = label
        self._statuses = statuses

    def compose(self) -> ComposeResult:
        yield Static(self._label, classes="column-header")
        with ScrollableContainer(classes="column-body", id=f"col-{self._label.lower()}"):
            pass

    def add_story_card(self, story: Story) -> None:
        col_body = self.query_one(f"#col-{self._label.lower()}", ScrollableContainer)
        card = StoryCard(story)
        col_body.mount(card)

    def contains_status(self, status: StoryStatus) -> bool:
        return status in self._statuses


class BoardScreen(Screen):
    """Main Kanban board screen."""

    TITLE = "AgentBoard"
    BINDINGS = [
        Binding("n", "new_story", "New Story"),
        Binding("enter", "open_story", "Open Story"),
        Binding("x", "delete_story", "Delete PRD"),
        Binding("h", "force_heartbeat", "Heartbeat"),
        Binding("q", "quit_app", "Quit"),
        Binding("?", "show_help", "Help"),
    ]

    DEFAULT_CSS = """
    BoardScreen {
        layout: vertical;
    }
    BoardScreen .board-area {
        height: 1fr;
        layout: horizontal;
    }
    """

    def compose(self) -> ComposeResult:
        from agentboard.tui.widgets.heartbeat_bar import HeartbeatBar

        yield Header()
        with Horizontal(classes="board-area"):
            for label, statuses in zip(_COLUMN_LABELS, _COLUMNS, strict=True):
                yield KanbanColumn(label=label, statuses=statuses)
        yield HeartbeatBar(id="heartbeat-bar")
        yield Footer()

    async def on_mount(self) -> None:
        await self.refresh_board()

    async def refresh_board(self) -> None:
        """Load stories from DB and populate columns."""
        async with get_session() as session:
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload

            stmt = select(Story).options(selectinload(Story.tickets))
            result = await session.execute(stmt)
            stories = result.scalars().all()

        # Clear all columns
        for label in _COLUMN_LABELS:
            col_body = self.query_one(f"#col-{label.lower()}", ScrollableContainer)
            col_body.remove_children()

        for story in stories:
            self._place_story(story)

    def _place_story(self, story: Story) -> None:
        """Place a story card in the appropriate column."""
        for label, statuses in zip(_COLUMN_LABELS, _COLUMNS, strict=True):
            if story.status in statuses:
                col_body = self.query_one(f"#col-{label.lower()}", ScrollableContainer)
                col_body.mount(StoryCard(story))
                return

    def action_new_story(self) -> None:
        """Open new story creation dialog."""
        from agentboard.tui.screens.story_detail import StoryDetailScreen

        self.app.push_screen(StoryDetailScreen(story=None))

    def action_open_story(self) -> None:
        """Open the focused story."""
        focused = self.focused
        if isinstance(focused, StoryCard):
            from agentboard.tui.screens.story_detail import StoryDetailScreen

            self.app.push_screen(StoryDetailScreen(story=focused._story))

    def action_force_heartbeat(self) -> None:
        """Trigger an immediate heartbeat check."""
        self.app.trigger_heartbeat()  # type: ignore[attr-defined]

    def action_quit_app(self) -> None:
        self.app.exit()

    def action_show_help(self) -> None:
        self.notify(
            "[n] New story  [Enter] Open  [x] Delete PRD  [h] Heartbeat  [q] Quit",
            title="Keyboard Shortcuts",
        )

    def action_delete_story(self) -> None:
        asyncio.create_task(self._do_delete_story())

    async def _do_delete_story(self) -> None:
        focused = self.focused
        if not isinstance(focused, StoryCard):
            self.notify("Focus a story card first.", severity="warning")
            return

        story = focused._story
        if not _can_delete_story(story.status):
            self.notify(
                "PRD deletion is only available during DRAFTING/REFINING.",
                severity="warning",
            )
            return

        confirmed = await self.app.push_screen_wait(DeletePRDConfirmScreen(story.title))
        if not confirmed:
            return

        async with get_session() as session:
            db_story = await session.get(Story, story.id)
            if db_story is not None:
                await session.delete(db_story)

        self.notify("PRD deleted.", title="Deleted")
        await self.refresh_board()

    def on_story_card_focus(self) -> None:
        pass

    async def on_story_updated(self, story_id: int) -> None:
        """Refresh board when a story status changes."""
        await self.refresh_board()
