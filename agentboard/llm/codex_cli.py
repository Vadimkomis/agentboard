"""CodexCLIClient — invokes the codex CLI as a subprocess.

Uses the user's OpenAI subscription (no API key required).
Codex is suited for single-file fixes, test generation, boilerplate, and well-scoped bugs.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from collections.abc import AsyncIterator, Callable
from pathlib import Path


class CodexCLIClient:
    """Invokes `codex exec <prompt>` as an asyncio subprocess."""

    def __init__(self, cli_path: str = "codex") -> None:
        self.cli_path = cli_path
        self._validate_cli()

    def _validate_cli(self) -> None:
        if not shutil.which(self.cli_path):
            raise RuntimeError(
                f"codex CLI not found at {self.cli_path!r}. "
                "Install with: npm install -g @openai/codex"
            )

    def _build_prompt(self, system: str, messages: list[dict[str, str]]) -> str:
        """Build a single prompt string from system + conversation history."""
        parts: list[str] = []
        if system:
            parts.append(f"System: {system}")
        for msg in messages:
            role = msg["role"].capitalize()
            parts.append(f"{role}: {msg['content']}")
        return "\n\n".join(parts)

    def _build_exec_cmd(
        self,
        prompt: str,
        *,
        workspace: str | None = None,
        output_last_message_file: str | None = None,
        json_output: bool = False,
    ) -> list[str]:
        cmd = [
            self.cli_path,
            "exec",
            prompt,
            "--full-auto",
            "--color",
            "never",
        ]
        if output_last_message_file:
            cmd.extend(["--output-last-message", output_last_message_file])
        if json_output:
            cmd.append("--json")
        if workspace:
            cmd.extend(["-C", workspace])
        return cmd

    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 4096,
    ) -> str:
        """Run completion and return full response text."""
        del max_tokens
        prompt = self._build_prompt(system, messages)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            output_file = tmp.name

        try:
            proc = await asyncio.create_subprocess_exec(
                *self._build_exec_cmd(prompt, output_last_message_file=output_file),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err = stderr.decode().strip()
                raise RuntimeError(f"codex CLI exited with code {proc.returncode}: {err}")

            response = Path(output_file).read_text(encoding="utf-8").strip()
            if response:
                return response

            fallback = stdout.decode().strip()
            if fallback:
                return fallback
            raise RuntimeError("codex CLI returned an empty response")
        finally:
            Path(output_file).unlink(missing_ok=True)

    async def stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        on_token: Callable[[str], None],
        *,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Stream response; codex exec provides stable non-interactive final output."""
        text = await self.complete(system, messages, max_tokens=max_tokens)
        if text:
            on_token(text)
            yield text

    async def run_agent(
        self,
        system: str,
        task: str,
        workspace: str,
        *,
        allowed_tools: list[str] | None = None,
        on_output: Callable[[str], None] | None = None,
    ) -> str:
        """Run codex as a headless coding agent in a workspace directory."""
        prompt = f"{system}\n\n{task}"
        proc = await asyncio.create_subprocess_exec(
            *self._build_exec_cmd(prompt, workspace=workspace),
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
            stderr_data = await proc.stderr.read() if proc.stderr else b""  # type: ignore[union-attr]
            err = stderr_data.decode().strip()
            raise RuntimeError(f"codex agent exited with code {proc.returncode}: {err}")

        return full_output
