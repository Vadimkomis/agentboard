"""Story detail screen — PRD editor + PM/Growth chat + ticket grid + finalize actions."""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    TabbedContent,
    TabPane,
    TextArea,
)

from agentboard.core.db import get_session
from agentboard.core.models import (
    GrowthMessage,
    MessageRole,
    Story,
    StoryMessage,
    StoryStatus,
)
from agentboard.tui.widgets.chat_panel import ChatPanel
from agentboard.tui.widgets.ticket_grid import TicketGrid


class PRDEditor(Vertical):
    """Editable PRD editor — left panel of story detail."""

    DEFAULT_CSS = """
    PRDEditor {
        width: 50%;
        height: 100%;
        padding: 0 1;
        border-right: solid $surface-lighten-1;
        overflow-y: auto;
    }
    PRDEditor Label {
        color: $text-muted;
        text-style: bold;
        margin-top: 1;
    }
    PRDEditor TextArea {
        height: 4;
        margin-bottom: 1;
    }
    PRDEditor Input {
        margin-bottom: 1;
    }
    """

    def __init__(self, story: Story | None, editable: bool = True, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._story = story
        self._editable = editable

    def compose(self) -> ComposeResult:
        story = self._story
        ro = not self._editable

        yield Label("Story Title")
        yield Input(
            value=story.title if story else "",
            placeholder="Auth flow with GitHub OAuth",
            id="prd-title",
            disabled=ro,
        )

        yield Label("Problem")
        yield TextArea(
            text=story.prd_problem or "" if story else "",
            id="prd-problem",
            disabled=ro,
        )

        yield Label("Solution")
        yield TextArea(
            text=story.prd_solution or "" if story else "",
            id="prd-solution",
            disabled=ro,
        )

        yield Label("Scope (In / Out)")
        yield TextArea(
            text=story.prd_scope or "" if story else "",
            id="prd-scope",
            disabled=ro,
        )

        yield Label("Acceptance Criteria")
        yield TextArea(
            text=story.prd_acceptance or "" if story else "",
            id="prd-acceptance",
            disabled=ro,
        )

        yield Label("GTM Strategy ⚠ (required to finalize)")
        yield TextArea(
            text=story.prd_gtm or "" if story else "",
            id="prd-gtm",
            disabled=ro,
        )

    def get_prd_values(self) -> dict[str, str]:
        """Extract current PRD field values."""
        return {
            "title": self.query_one("#prd-title", Input).value,
            "problem": self.query_one("#prd-problem", TextArea).text,
            "solution": self.query_one("#prd-solution", TextArea).text,
            "scope": self.query_one("#prd-scope", TextArea).text,
            "acceptance": self.query_one("#prd-acceptance", TextArea).text,
            "gtm": self.query_one("#prd-gtm", TextArea).text,
        }


class StoryDetailScreen(Screen):
    """Story detail: PRD editor + PM/Growth chat panels + finalize actions."""

    TITLE = "Story Detail"
    BINDINGS = [
        Binding("f", "finalize_pm", "Finalize PM →"),
        Binding("g", "finalize_growth", "Finalize Growth →"),
        Binding("d", "mark_done", "Mark Done"),
        Binding("q,escape", "go_back", "Back"),
        Binding("tab", "switch_chat", "Switch Chat"),
    ]

    DEFAULT_CSS = """
    StoryDetailScreen {
        layout: vertical;
    }
    StoryDetailScreen .main-row {
        height: 1fr;
        layout: horizontal;
    }
    StoryDetailScreen .right-panel {
        width: 50%;
        height: 100%;
        layout: vertical;
    }
    StoryDetailScreen .action-bar {
        height: 3;
        layout: horizontal;
        align: center middle;
        background: $surface-darken-1;
        padding: 0 1;
    }
    StoryDetailScreen .action-bar Button {
        margin: 0 1;
    }
    """

    def __init__(self, story: Story | None, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._story = story
        self._is_new = story is None
        self._pm_chat: ChatPanel | None = None
        self._growth_chat: ChatPanel | None = None
        self._current_chat = "pm"

    def compose(self) -> ComposeResult:
        yield Header()

        editable = self._is_new or (
            self._story and self._story.status in (StoryStatus.drafting, StoryStatus.refining)
        )

        with Horizontal(classes="main-row"):
            yield PRDEditor(story=self._story, editable=bool(editable), id="prd-editor")

            with Vertical(classes="right-panel"):
                with TabbedContent(id="chat-tabs"):
                    with TabPane("PM Agent", id="tab-pm"):
                        yield ChatPanel(
                            agent_name="PM Agent",
                            placeholder="Describe your story or ask questions...",
                            id="pm-chat",
                        )
                    with TabPane("Growth Agent", id="tab-growth"):
                        yield ChatPanel(
                            agent_name="Growth Agent",
                            placeholder="Talk through your GTM strategy...",
                            id="growth-chat",
                        )

                # Show ticket grid if story is past DRAFTING
                if self._story and self._story.status not in (
                    StoryStatus.drafting,
                    StoryStatus.refining,
                ):
                    yield TicketGrid(id="ticket-grid")

        with Horizontal(classes="action-bar"):
            yield Button("[f] Finalize PM → tickets", id="btn-finalize-pm", variant="primary")
            yield Button(
                "[g] Finalize Growth → LAUNCH.md", id="btn-finalize-growth", variant="success"
            )
            if self._story and self._story.status == StoryStatus.testing:
                yield Button("[d] Mark Done", id="btn-mark-done", variant="warning")

        yield Footer()

    async def on_mount(self) -> None:
        self._pm_chat = self.query_one("#pm-chat", ChatPanel)
        self._growth_chat = self.query_one("#growth-chat", ChatPanel)

        # Wire send handlers
        self._pm_chat.set_send_handler(self._on_pm_message)
        self._growth_chat.set_send_handler(self._on_growth_message)

        # Load existing messages
        if self._story:
            await self._load_history()
            # Load ticket grid
            try:
                grid = self.query_one("#ticket-grid", TicketGrid)
                await self.app.refresh_story(self._story)  # type: ignore[attr-defined]
                grid.load_tickets(self._story.tickets)
            except Exception:
                pass

        # If new story, seed PM chat with a welcome
        if self._is_new and self._pm_chat:
            self._pm_chat.add_message(
                "assistant",
                "Let's build something great! Tell me about your story — what problem are you solving?",
            )

    async def _load_history(self) -> None:
        """Load PM and Growth message history from DB."""
        if not self._story:
            return
        async with get_session() as session:
            from sqlalchemy import select

            pm_stmt = (
                select(StoryMessage)
                .where(StoryMessage.story_id == self._story.id)
                .order_by(StoryMessage.id)
            )
            growth_stmt = (
                select(GrowthMessage)
                .where(GrowthMessage.story_id == self._story.id)
                .order_by(GrowthMessage.id)
            )

            pm_result = await session.execute(pm_stmt)
            growth_result = await session.execute(growth_stmt)

            for msg in pm_result.scalars():
                if self._pm_chat:
                    self._pm_chat.add_message(msg.role.value, msg.content)

            for msg in growth_result.scalars():
                if self._growth_chat:
                    self._growth_chat.add_message(msg.role.value, msg.content)

    def _on_pm_message(self, text: str) -> None:
        """Handle user sending a PM chat message."""
        asyncio.create_task(self._handle_pm_message(text))

    def _on_growth_message(self, text: str) -> None:
        """Handle user sending a Growth chat message."""
        asyncio.create_task(self._handle_growth_message(text))

    async def _ensure_story_exists(self) -> Story:
        """Create story if new, return existing otherwise."""
        if self._story is not None:
            return self._story

        prd = self.query_one("#prd-editor", PRDEditor).get_prd_values()
        async with get_session() as session:
            story = Story(
                title=prd["title"] or "Untitled Story",
                prd_problem=prd["problem"] or None,
                prd_solution=prd["solution"] or None,
                prd_scope=prd["scope"] or None,
                prd_acceptance=prd["acceptance"] or None,
                prd_gtm=prd["gtm"] or None,
                status=StoryStatus.drafting,
            )
            session.add(story)
            await session.flush()
            self._story = story
            self._is_new = False
        return story

    async def _handle_pm_message(self, text: str) -> None:
        """Stream a PM agent response to the user's message."""
        if not self._pm_chat:
            return

        story = await self._ensure_story_exists()
        self._pm_chat.start_streaming()

        # Save user message
        async with get_session() as session:
            user_msg = StoryMessage(
                story_id=story.id,
                role=MessageRole.user,
                content=text,
            )
            session.add(user_msg)

        # Stream PM response
        pm_agent = self.app.pm_agent  # type: ignore[attr-defined]
        history = await self._load_pm_history(story.id)

        full_response = ""
        try:
            async for token in await pm_agent.refine(
                story=story,
                user_message=text,
                history=history,
                on_token=self._pm_chat.append_token,
            ):
                full_response += token
        except Exception as e:
            self._pm_chat.finish_streaming()
            self._pm_chat.add_message("assistant", f"Error: {e}")
            return

        self._pm_chat.finish_streaming()

        # Save assistant response
        async with get_session() as session:
            asst_msg = StoryMessage(
                story_id=story.id,
                role=MessageRole.assistant,
                content=full_response,
            )
            session.add(asst_msg)

    async def _handle_growth_message(self, text: str) -> None:
        """Stream a Growth agent response."""
        if not self._growth_chat:
            return

        story = await self._ensure_story_exists()
        self._growth_chat.start_streaming()

        # Save user message
        async with get_session() as session:
            user_msg = GrowthMessage(
                story_id=story.id,
                role=MessageRole.user,
                content=text,
            )
            session.add(user_msg)

        growth_agent = self.app.growth_agent  # type: ignore[attr-defined]
        history = await self._load_growth_history(story.id)

        full_response = ""
        try:
            async for token in await growth_agent.refine(
                story=story,
                user_message=text,
                history=history,
                on_token=self._growth_chat.append_token,
            ):
                full_response += token
        except Exception as e:
            self._growth_chat.finish_streaming()
            self._growth_chat.add_message("assistant", f"Error: {e}")
            return

        self._growth_chat.finish_streaming()

        # Save assistant response
        async with get_session() as session:
            asst_msg = GrowthMessage(
                story_id=story.id,
                role=MessageRole.assistant,
                content=full_response,
            )
            session.add(asst_msg)

    async def _load_pm_history(self, story_id: int) -> list[StoryMessage]:
        async with get_session() as session:
            from sqlalchemy import select

            stmt = (
                select(StoryMessage)
                .where(StoryMessage.story_id == story_id)
                .order_by(StoryMessage.id)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def _load_growth_history(self, story_id: int) -> list[GrowthMessage]:
        async with get_session() as session:
            from sqlalchemy import select

            stmt = (
                select(GrowthMessage)
                .where(GrowthMessage.story_id == story_id)
                .order_by(GrowthMessage.id)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    def action_finalize_pm(self) -> None:
        asyncio.create_task(self._do_finalize_pm())

    async def _do_finalize_pm(self) -> None:
        """Finalize PM: save PRD, decompose, start engineering."""
        story = await self._ensure_story_exists()

        # Save latest PRD values, resolving effective values via fallback to DB
        prd = self.query_one("#prd-editor", PRDEditor).get_prd_values()
        effective: dict[str, str] = {}
        async with get_session() as session:
            db_story = await session.get(Story, story.id)
            if db_story:
                effective["title"] = prd["title"] or db_story.title or ""
                effective["problem"] = prd["problem"] or db_story.prd_problem or ""
                effective["solution"] = prd["solution"] or db_story.prd_solution or ""
                effective["scope"] = prd["scope"] or db_story.prd_scope or ""
                effective["acceptance"] = prd["acceptance"] or db_story.prd_acceptance or ""
                effective["gtm"] = prd["gtm"] or db_story.prd_gtm or ""
                db_story.title = effective["title"]
                db_story.prd_problem = effective["problem"]
                db_story.prd_solution = effective["solution"]
                db_story.prd_scope = effective["scope"]
                db_story.prd_acceptance = effective["acceptance"]
                db_story.prd_gtm = effective["gtm"]
            else:
                effective = {
                    k: prd.get(k, "")
                    for k in ("title", "problem", "solution", "scope", "acceptance", "gtm")
                }

        # Validate against effective persisted values, not raw editor input
        if not all(effective.values()):
            self.notify("PRD is incomplete — fill all sections including GTM", severity="warning")
            return

        self.notify("Decomposing story into tickets...", title="PM Finalizing")

        try:
            pm_agent = self.app.pm_agent  # type: ignore[attr-defined]
            # Re-fetch story so pm_agent sees the saved PRD values
            async with get_session() as session:
                story = await session.get(Story, story.id) or story  # type: ignore[assignment]
            decomposed = await pm_agent.decompose(story)

            orchestrator = self.app.orchestrator  # type: ignore[attr-defined]
            async with get_session() as session:
                db_story = await session.get(Story, story.id)
                if db_story:
                    await orchestrator.decompose_and_start(db_story, decomposed, session)

            self.notify(
                f"Created {len(decomposed.engineering_tickets)} tickets — engineering started!",
                title="Story finalized",
            )
            self.action_go_back()

        except Exception as e:
            self.notify(f"Finalize failed: {e}", severity="error")

    def action_finalize_growth(self) -> None:
        asyncio.create_task(self._do_finalize_growth())

    async def _do_finalize_growth(self) -> None:
        """Generate LAUNCH.md from growth conversation."""
        story = await self._ensure_story_exists()
        self.notify("Generating LAUNCH.md...", title="Growth Finalizing")

        try:
            history = await self._load_growth_history(story.id)
            if not history:
                self.notify("Start a growth conversation first", severity="warning")
                return

            growth_agent = self.app.growth_agent  # type: ignore[attr-defined]
            await growth_agent.generate_launch_md(story, history)

            # Save to story — actual commit happens via engineering_runner
            async with get_session() as session:
                db_story = await session.get(Story, story.id)
                if db_story:
                    db_story.launch_md_finalized = True
                    self._story = db_story

            self.notify(
                "LAUNCH.md generated! (Commit it via the engineering runner)", title="Growth Done"
            )

        except Exception as e:
            self.notify(f"Growth finalize failed: {e}", severity="error")

    def action_mark_done(self) -> None:
        asyncio.create_task(self._do_mark_done())

    async def _do_mark_done(self) -> None:
        if not self._story:
            return
        async with get_session() as session:
            db_story = await session.get(Story, self._story.id)
            if db_story:
                db_story.status = StoryStatus.done
        self.notify("Story marked as done!", title="Done")
        self.action_go_back()

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_switch_chat(self) -> None:
        """Toggle between PM and Growth chat panels."""
        tabs = self.query_one("#chat-tabs", TabbedContent)
        if self._current_chat == "pm":
            tabs.active = "tab-growth"
            self._current_chat = "growth"
        else:
            tabs.active = "tab-pm"
            self._current_chat = "pm"

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-finalize-pm":
            self.action_finalize_pm()
        elif event.button.id == "btn-finalize-growth":
            self.action_finalize_growth()
        elif event.button.id == "btn-mark-done":
            self.action_mark_done()
