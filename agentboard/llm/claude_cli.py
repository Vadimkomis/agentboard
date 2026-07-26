"""ClaudeCLIClient — invokes the claude CLI as a subprocess.

Uses the user's Claude subscription (no API key required).
Conversation history is passed as a single prompt string; the CLI is stateless.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import AsyncIterator, Callable


class ClaudeCLIClient:
    """Invokes `claude -p <prompt>` as an asyncio subprocess.

    The claude CLI is stateless per call. We pass the full conversation
    history embedded in the prompt on every call.
    """

    def __init__(self, cli_path: str = "claude") -> None:
        self.cli_path = cli_path
        self._validate_cli()

    def _validate_cli(self) -> None:
        if not shutil.which(self.cli_path):
            raise RuntimeError(
                f"claude CLI not found at {self.cli_path!r}. "
                "Install with: npm install -g @anthropic-ai/claude-code"
            )

    def _build_prompt(self, system: str, messages: list[dict[str, str]]) -> str:
        """Build a single prompt string from system + conversation history."""
        parts: list[str] = []
        if system:
            parts.append(f"<system>\n{system}\n</system>")
        for msg in messages:
            role = msg["role"].upper()
            content = msg["content"]
            parts.append(f"<{role}>\n{content}\n</{role}>")
        return "\n\n".join(parts)

    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 4096,
    ) -> str:
        """Run completion and return full response text."""
        prompt = self._build_prompt(system, messages)
        proc = await asyncio.create_subprocess_exec(
            self.cli_path,
            "-p",
            prompt,
            "--output-format",
            "text",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            err = stderr.decode().strip()
            raise RuntimeError(f"claude CLI exited with code {proc.returncode}: {err}")
        return stdout.decode().strip()

    async def stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        on_token: Callable[[str], None],
        *,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Stream response tokens, calling on_token for each chunk."""
        prompt = self._build_prompt(system, messages)
        proc = await asyncio.create_subprocess_exec(
            self.cli_path,
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdout is not None
        full_text = ""
        async for raw_line in proc.stdout:
            line = raw_line.decode().strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # Plain text fallback (non-streaming mode)
                on_token(line)
                full_text += line
                yield line
                continue
            # Handle stream-json events
            event_type = event.get("type", "")
            if event_type == "content_block_delta":
                delta = event.get("delta", {})
                text = delta.get("text", "")
                if text:
                    on_token(text)
                    full_text += text
                    yield text
            elif event_type == "message_stop":
                break

        await proc.wait()
        if proc.returncode not in (0, None):
            stderr_data = await proc.stderr.read() if proc.stderr else b""
            err = stderr_data.decode().strip()
            raise RuntimeError(f"claude CLI exited with code {proc.returncode}: {err}")

    async def run_agent(
        self,
        system: str,
        task: str,
        workspace: str,
        *,
        allowed_tools: list[str] | None = None,
        on_output: Callable[[str], None] | None = None,
    ) -> str:
        """Run claude as a headless coding agent in a workspace directory.

        Uses `claude --dangerously-skip-permissions` for non-interactive execution.
        Returns the full stdout output.
        """
        cmd = [
            self.cli_path,
            "-p",
            f"{system}\n\n{task}",
            "--dangerously-skip-permissions",
            "--output-format",
            "text",
        ]
        if allowed_tools:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdout is not None

        output_chunks: list[str] = []
        async for raw_line in proc.stdout:
            chunk = raw_line.decode()
            output_chunks.append(chunk)
            if on_output:
                on_output(chunk)

        await proc.wait()
        full_output = "".join(output_chunks)

        if proc.returncode != 0:
            stderr_data = await proc.stderr.read() if proc.stderr else b""
            err = stderr_data.decode().strip()
            raise RuntimeError(f"claude agent exited with code {proc.returncode}: {err}")

        return full_output
