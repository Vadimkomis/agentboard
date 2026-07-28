"""Behavior tests for browser-specific CLI entry points."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentboard.application import GetProjectWorkspace
from agentboard.cli import app
from agentboard.infrastructure.database import Database


def test_create_project_command_makes_a_project_visible_to_browser_queries(
    tmp_path: Path,
) -> None:
    path = tmp_path / "browser.db"
    result = CliRunner().invoke(
        app,
        [
            "create-project",
            "AB",
            "AgentBoard",
            "https://github.com/example/agentboard",
            "--db",
            str(path),
        ],
    )

    async def read_project() -> tuple[str, str]:
        database = Database(path)
        try:
            workspace = await GetProjectWorkspace(database.unit_of_work)(project_key="AB")
            return workspace.project.key, workspace.project.name
        finally:
            await database.dispose()

    assert result.exit_code == 0
    assert "Created AB (AgentBoard)" in result.stdout
    assert asyncio.run(read_project()) == ("AB", "AgentBoard")


def test_create_project_command_reports_invalid_url_unsafe_key(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "create-project",
            "A/B",
            "Broken",
            "https://github.com/example/broken",
            "--db",
            str(tmp_path / "browser.db"),
        ],
    )

    assert result.exit_code == 1
    assert "letters, numbers, hyphens, and underscores" in result.stderr


def test_web_command_requires_owner_credentials() -> None:
    result = CliRunner().invoke(app, ["web"], env={})

    assert result.exit_code == 2
    assert "AGENTBOARD_OWNER_PASSWORD_HASH" in result.stderr


@pytest.mark.parametrize("host", ["0.0.0.0", "::1"])
def test_web_command_rejects_unsupported_binding(
    host: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("uvicorn.run", lambda *_args, **_kwargs: None)
    result = CliRunner().invoke(
        app,
        ["web", "--host", host],
        env={
            "AGENTBOARD_OWNER_PASSWORD_HASH": "hash",
            "AGENTBOARD_SESSION_SECRET": "a-secure-session-secret-that-is-long",
        },
    )

    assert result.exit_code == 2
    assert "SSH tunnel" in result.stderr
