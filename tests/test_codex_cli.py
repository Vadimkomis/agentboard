from __future__ import annotations

from pathlib import Path

import pytest

from agentboard.llm import codex_cli
from agentboard.llm.codex_cli import CodexCLIClient


class _CompleteProc:
    def __init__(self, *, returncode: int, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


class _BytesAsyncIter:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self._index = 0

    def __aiter__(self) -> _BytesAsyncIter:
        return self

    async def __anext__(self) -> bytes:
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        item = self._chunks[self._index]
        self._index += 1
        return item


class _StderrReader:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data


class _StreamingProc:
    def __init__(self, *, chunks: list[bytes], returncode: int = 0, stderr: bytes = b"") -> None:
        self.stdout = _BytesAsyncIter(chunks)
        self.stderr = _StderrReader(stderr)
        self.returncode = returncode

    async def wait(self) -> None:
        return None


@pytest.mark.asyncio
async def test_complete_uses_codex_exec_and_output_last_message(monkeypatch):
    monkeypatch.setattr(codex_cli.shutil, "which", lambda _path: "/usr/bin/codex")
    captured: dict[str, tuple[str, ...]] = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        del kwargs
        captured["args"] = tuple(args)
        output_idx = args.index("--output-last-message")
        output_file = args[output_idx + 1]
        Path(output_file).write_text("PM response", encoding="utf-8")
        return _CompleteProc(returncode=0)

    monkeypatch.setattr(codex_cli.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    client = CodexCLIClient("codex")
    result = await client.complete("System prompt", [{"role": "user", "content": "hello"}])

    assert result == "PM response"
    assert captured["args"][:2] == ("codex", "exec")
    assert "--full-auto" in captured["args"]
    assert "--output-last-message" in captured["args"]


@pytest.mark.asyncio
async def test_complete_raises_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(codex_cli.shutil, "which", lambda _path: "/usr/bin/codex")

    async def fake_create_subprocess_exec(*args, **kwargs):
        del args, kwargs
        return _CompleteProc(returncode=2, stderr=b"boom")

    monkeypatch.setattr(codex_cli.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    client = CodexCLIClient("codex")
    with pytest.raises(RuntimeError, match="exited with code 2: boom"):
        await client.complete("S", [{"role": "user", "content": "x"}])


@pytest.mark.asyncio
async def test_stream_emits_complete_text(monkeypatch):
    monkeypatch.setattr(codex_cli.shutil, "which", lambda _path: "/usr/bin/codex")
    client = CodexCLIClient("codex")

    async def fake_complete(*args, **kwargs):
        del args, kwargs
        return "final chunk"

    monkeypatch.setattr(client, "complete", fake_complete)

    seen: list[str] = []
    chunks = [
        token
        async for token in client.stream(
            "System",
            [{"role": "user", "content": "hello"}],
            on_token=seen.append,
        )
    ]

    assert chunks == ["final chunk"]
    assert seen == ["final chunk"]


@pytest.mark.asyncio
async def test_run_agent_uses_exec_and_streams_output(monkeypatch):
    monkeypatch.setattr(codex_cli.shutil, "which", lambda _path: "/usr/bin/codex")
    captured: dict[str, tuple[str, ...]] = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        del kwargs
        captured["args"] = tuple(args)
        return _StreamingProc(chunks=[b"line 1\n", b"TASK_COMPLETE\n"])

    monkeypatch.setattr(codex_cli.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    outputs: list[str] = []
    client = CodexCLIClient("codex")
    result = await client.run_agent(
        system="System",
        task="Do work",
        workspace="/tmp/workspace",
        on_output=outputs.append,
    )

    assert result == "line 1\nTASK_COMPLETE\n"
    assert outputs == ["line 1\n", "TASK_COMPLETE\n"]
    assert captured["args"][:2] == ("codex", "exec")
    assert "-C" in captured["args"]
    c_index = captured["args"].index("-C")
    assert captured["args"][c_index + 1] == "/tmp/workspace"
