"""Ticket grid widget — shows all tickets for a story with status and dependencies."""

from __future__ import annotations

import contextlib

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import DataTable, Label

from agentboard.core.models import Ticket, TicketStatus

_STATUS_ICONS = {
    TicketStatus.pending: "○",
    TicketStatus.in_progress: "●",
    TicketStatus.done: "✓",
    TicketStatus.failed: "✗",
    TicketStatus.cancelled: "⊘",
}


class TicketGrid(Widget):
    """DataTable showing all tickets in a story with status, agent, and deps."""

    DEFAULT_CSS = """
    TicketGrid {
        height: 100%;
    }
    TicketGrid Label {
        padding: 0 1;
        color: $text-muted;
        text-style: bold;
    }
    TicketGrid DataTable {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("Tickets")
        yield DataTable(id="ticket-table")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("", "Title", "Agent", "Runtime", "Priority", "Depends On", "PR")

    def load_tickets(self, tickets: list[Ticket]) -> None:
        """Populate the grid with ticket data."""
        table = self.query_one(DataTable)
        table.clear()

        for ticket in sorted(tickets, key=lambda t: t.ticket_index):
            icon = _STATUS_ICONS.get(ticket.status, "?")
            title = ticket.title[:50]
            agent = ticket.agent_type.value
            runtime = ticket.runtime.value
            priority = ticket.priority
            dep = f"→ #{ticket.depends_on_index}" if ticket.depends_on_index is not None else ""
            pr = "✓" if ticket.pr_url else ""

            table.add_row(icon, title, agent, runtime, priority, dep, pr, key=str(ticket.id))

    def update_ticket_status(self, ticket_id: int, status: TicketStatus) -> None:
        """Update a single ticket's status icon in-place."""
        table = self.query_one(DataTable)
        icon = _STATUS_ICONS.get(status, "?")
        with contextlib.suppress(Exception):
            table.update_cell(str(ticket_id), "", icon)
