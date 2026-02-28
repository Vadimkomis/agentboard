"""Reusable streaming chat widget — shared by PM and Growth agents."""

from __future__ import annotations

from collections.abc import Callable

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Label, Markdown, Static


class MessageBubble(Static):
    """A single chat message bubble."""

    DEFAULT_CSS = """
    MessageBubble {
        padding: 0 1;
        margin-bottom: 1;
    }
    MessageBubble.user {
        background: $primary-darken-2;
        color: $text;
        margin-left: 4;
    }
    MessageBubble.assistant {
        background: $surface-lighten-1;
        color: $text;
        margin-right: 4;
    }
    MessageBubble .role-label {
        color: $text-muted;
        text-style: bold;
    }
    """

    def __init__(self, role: str, content: str, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._role = role
        self._content = content
        self.add_class(role)

    def compose(self) -> ComposeResult:
        yield Label(self._role.upper(), classes="role-label")
        yield Markdown(self._content)


class ChatPanel(Widget):
    """Streaming chat panel — displays conversation and accepts user input.

    Usage:
        panel = ChatPanel(agent_name="PM Agent", on_send=my_handler)
        # Call panel.append_token() to stream tokens in real time
        # Call panel.add_message() to add a complete message
    """

    DEFAULT_CSS = """
    ChatPanel {
        layout: vertical;
        height: 100%;
    }
    ChatPanel .messages-container {
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
    }
    ChatPanel .streaming-indicator {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    ChatPanel .input-row {
        height: 3;
        layout: horizontal;
        padding: 0 1;
    }
    ChatPanel .input-row Input {
        width: 1fr;
    }
    ChatPanel .agent-title {
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }
    """

    is_streaming: reactive[bool] = reactive(False)
    _current_stream_text: str = ""

    def __init__(
        self,
        agent_name: str = "Agent",
        placeholder: str = "Type a message...",
        on_send: Callable[[str], None] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._agent_name = agent_name
        self._placeholder = placeholder
        self._on_send = on_send
        self._messages: list[tuple[str, str]] = []
        self._streaming_label: Static | None = None

    def compose(self) -> ComposeResult:
        yield Static(self._agent_name, classes="agent-title")
        with ScrollableContainer(classes="messages-container") as self._scroll:
            pass
        yield Static("", classes="streaming-indicator", id="streaming-indicator")
        with Vertical(classes="input-row"):
            yield Input(placeholder=self._placeholder, id="chat-input")

    def on_mount(self) -> None:
        self._streaming_widget = self.query_one("#streaming-indicator", Static)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.value = ""
        self.add_message("user", text)
        if self._on_send:
            self._on_send(text)

    def add_message(self, role: str, content: str) -> None:
        """Add a complete message to the chat."""
        self._messages.append((role, content))
        self._scroll.mount(MessageBubble(role, content))
        self._scroll.scroll_end(animate=False)

    def start_streaming(self) -> None:
        """Indicate that the agent is generating a response."""
        self.is_streaming = True
        self._current_stream_text = ""
        self._streaming_widget.update("● generating...")

    def append_token(self, token: str) -> None:
        """Append a streaming token to the current response."""
        self._current_stream_text += token
        # Show last 100 chars of current response in indicator
        preview = self._current_stream_text[-80:].replace("\n", " ")
        self._streaming_widget.update(f"● {preview}")

    def finish_streaming(self) -> None:
        """Mark streaming complete and add the full message."""
        self.is_streaming = False
        self._streaming_widget.update("")
        if self._current_stream_text:
            self.add_message("assistant", self._current_stream_text)
            self._current_stream_text = ""

    def clear(self) -> None:
        """Clear all messages."""
        self._messages.clear()
        self._scroll.remove_children()

    def set_send_handler(self, handler: Callable[[str], None]) -> None:
        self._on_send = handler

    def focus_input(self) -> None:
        self.query_one("#chat-input", Input).focus()
