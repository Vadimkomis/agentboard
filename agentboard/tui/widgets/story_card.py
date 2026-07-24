"""Story card widget — shown on the Kanban board."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static

from agentboard.core.models import Story, StoryStatus

_STATUS_LABELS = {
    StoryStatus.drafting: "Drafting",
    StoryStatus.refining: "Refining",
    StoryStatus.decomposing: "Decomposing...",
    StoryStatus.engineering: "Engineering",
    StoryStatus.testing: "Testing",
    StoryStatus.done: "Done ✓",
}

_AGENT_BADGE_MAP = {
    "backend": "BE",
    "frontend": "FE",
    "mobile": "MOB",
    "devops": "OPS",
    "qa": "QA",
    "fullstack": "FS",
    "docs": "DOC",
    "marketing": "MKT",
}


class StoryCard(Widget):
    """Story card displayed in a Kanban column.

    Shows: title, status, progress bar (ENGINEERING), agent badges,
    GTM warning, LAUNCH.md status, bug count.
    """

    DEFAULT_CSS = """
    StoryCard {
        height: auto;
        min-height: 6;
        margin: 0 1 1 1;
        padding: 1;
        background: $surface;
        border: solid $primary-darken-2;
        border-title-color: $primary;
    }
    StoryCard:hover {
        border: solid $primary;
    }
    StoryCard:focus {
        border: solid $accent;
    }
    StoryCard .card-title {
        text-style: bold;
        color: $text;
        margin-bottom: 0;
    }
    StoryCard .card-status {
        color: $text-muted;
        margin-bottom: 0;
    }
    StoryCard .card-badges {
        color: $accent;
        margin-top: 0;
    }
    StoryCard .card-warning {
        color: $warning;
    }
    StoryCard .card-bug {
        color: $error;
    }
    StoryCard .card-launch {
        color: $success;
    }
    """

    can_focus = True

    def __init__(self, story: Story, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._story = story
        self.id = f"story-card-{story.id}"

    def compose(self) -> ComposeResult:
        story = self._story
        yield Static(story.title[:40], classes="card-title")
        yield Static(_STATUS_LABELS.get(story.status, story.status.value), classes="card-status")

        # Progress bar in ENGINEERING
        if story.status == StoryStatus.engineering and story.ticket_total > 0:
            done = story.ticket_done_count
            total = story.ticket_total
            yield Static(
                f"{'█' * done}{'░' * (total - done)} {done}/{total}", classes="card-badges"
            )

        # Agent type badges
        agent_types = {
            t.agent_type.value for t in story.tickets if t.agent_type.value != "marketing"
        }
        if agent_types:
            badges = " ".join(_AGENT_BADGE_MAP.get(a, a.upper()) for a in sorted(agent_types))
            yield Static(badges, classes="card-badges")

        # GTM warning
        if not story.gtm_complete and story.status in (
            StoryStatus.drafting,
            StoryStatus.refining,
            StoryStatus.engineering,
        ):
            yield Static("[GTM ⚠]", classes="card-warning")

        # LAUNCH.md status
        if story.launch_md_finalized:
            yield Static("📄 LAUNCH.md ready", classes="card-launch")
        elif story.marketing_ticket is not None:
            yield Static("📄 launch in progress", classes="card-badges")

        # Bug count in TESTING
        if story.status == StoryStatus.testing and story.open_bug_count > 0:
            yield Static(
                f"🐛 {story.open_bug_count} bug{'s' if story.open_bug_count > 1 else ''}",
                classes="card-bug",
            )

        # Stale ticket warning
        if story.stale_ticket_count > 0:
            yield Static(
                f"⚠ {story.stale_ticket_count} stale ticket{'s' if story.stale_ticket_count > 1 else ''}",
                classes="card-warning",
            )

    def update_story(self, story: Story) -> None:
        """Re-render the card with updated story data."""
        self._story = story
        self.refresh(recompose=True)

    def on_click(self) -> None:
        self.focus()

    def on_key(self, event: object) -> None:
        pass  # Handled by parent screen
