"""Heartbeat status bar widget — displayed in the app footer."""

from __future__ import annotations

from datetime import UTC, datetime

from textual.reactive import reactive
from textual.widgets import Static


class HeartbeatBar(Static):
    """Footer status bar showing last heartbeat time and status."""

    DEFAULT_CSS = """
    HeartbeatBar {
        dock: bottom;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    HeartbeatBar.ok {
        color: $success;
    }
    HeartbeatBar.alert {
        color: $warning;
    }
    HeartbeatBar.error {
        color: $error;
    }
    """

    last_check: reactive[datetime | None] = reactive(None)
    status_text: reactive[str] = reactive("Not checked yet")
    is_alert: reactive[bool] = reactive(False)

    def render(self) -> str:
        if self.last_check is None:
            return "♥ Never checked"

        now = datetime.now(UTC)
        last = self.last_check
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)

        delta = now - last
        seconds = int(delta.total_seconds())

        if seconds < 60:
            time_str = f"{seconds}s ago"
        elif seconds < 3600:
            time_str = f"{seconds // 60}min ago"
        else:
            time_str = f"{seconds // 3600}h ago"

        if self.is_alert:
            return f"♥ {time_str} ⚠ {self.status_text}"
        return f"♥ {time_str} OK"

    def update_status(self, check_time: datetime, result: str) -> None:
        """Called by heartbeat monitor when a check completes."""
        self.last_check = check_time
        self.is_alert = result.strip() != "HEARTBEAT_OK"
        self.status_text = result.strip() if self.is_alert else "OK"

        if self.is_alert:
            self.add_class("alert")
            self.remove_class("ok")
            self.remove_class("error")
        else:
            self.add_class("ok")
            self.remove_class("alert")
            self.remove_class("error")
