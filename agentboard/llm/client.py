"""LLMClient Protocol — unified interface for all LLM backends."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Unified interface for LLM backends (Claude CLI, Codex CLI, etc.)."""

    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 4096,
    ) -> str:
        """Run a blocking completion and return the full response text."""
        ...

    async def stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        on_token: Callable[[str], None],
        *,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Stream response tokens, calling on_token for each chunk."""
        ...
