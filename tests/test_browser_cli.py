"""Behavior tests for browser-specific CLI entry points."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from agentboard.application import GetProjectWorkspace, ListProjects
from agentboard.cli import app
from agentboard.infrastructure.database import Database
from agentboard.web import WebSettings, create_app


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


def test_seed_demo_command_populates_every_browser_view(tmp_path: Path) -> None:
    path = tmp_path / "browser.db"
    result = CliRunner().invoke(app, ["seed-demo", "--db", str(path)])

    async def render_views() -> tuple[str, ...]:
        settings = WebSettings(
            database_path=path,
            session_secret="test-session-secret-that-is-long-enough-for-hmac",
            allowed_hosts=("testserver",),
        )
        browser = create_app(settings)
        async with browser.router.lifespan_context(browser):
            transport = httpx.ASGITransport(app=browser)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                responses = [
                    await client.get("/projects/DEMO/backlog"),
                    await client.get("/projects/DEMO/board"),
                    await client.get("/projects/DEMO/features/2"),
                    await client.get("/projects/DEMO/approvals"),
                    await client.get("/projects/DEMO/reports"),
                ]
                assert all(response.status_code == 200 for response in responses)
                return tuple(response.text for response in responses)

    backlog, board, detail, approvals, reports = asyncio.run(render_views())

    assert result.exit_code == 0
    assert "Created DEMO (AgentBoard Demo)" in result.stdout
    assert "Current Sprint" in backlog
    assert "Define notification preferences" in backlog
    assert "data-reorder-form" in backlog
    assert board.count("data-board-column=") == 5
    assert "Publish seeded workspace" in board
    assert "Prepare browser workspace" in detail
    assert "Design approval" in approvals
    assert "Approve release candidate" in approvals
    assert "Sprint 1" in reports
    assert "Ship project foundation" in reports


def test_seed_demo_command_refuses_to_modify_an_existing_demo(tmp_path: Path) -> None:
    path = tmp_path / "browser.db"
    existing = CliRunner().invoke(
        app,
        [
            "create-project",
            "AB",
            "Existing Project",
            "https://github.com/example/existing",
            "--db",
            str(path),
        ],
    )
    first = CliRunner().invoke(app, ["seed-demo", "--db", str(path)])
    second = CliRunner().invoke(app, ["seed-demo", "--db", str(path)])

    async def counts() -> tuple[int, int, int]:
        database = Database(path)
        try:
            projects = await ListProjects(database.unit_of_work)()
            demo = await GetProjectWorkspace(database.unit_of_work)(project_key="DEMO")
            preserved = await GetProjectWorkspace(database.unit_of_work)(project_key="AB")
            active_count = len(demo.active_sprint.features) if demo.active_sprint else 0
            return (
                len(projects),
                len(demo.future_backlog) + active_count,
                len(preserved.future_backlog),
            )
        finally:
            await database.dispose()

    assert existing.exit_code == 0
    assert first.exit_code == 0
    assert second.exit_code == 1
    assert "Project key 'DEMO' already exists" in second.stderr
    assert asyncio.run(counts()) == (2, 9, 0)


def test_web_command_starts_without_owner_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[object] = []

    def capture_app(application: object, **_options: object) -> None:
        started.append(application)

    monkeypatch.setattr("uvicorn.run", capture_app)
    result = CliRunner().invoke(
        app,
        ["web", "--db", str(tmp_path / "browser.db")],
        env={},
    )

    assert result.exit_code == 0
    assert len(started) == 1
    assert started[0].state.web_settings.owner_password_hash is None


def test_web_command_enables_optional_owner_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[object] = []
    secret = "a-secure-session-secret-that-is-long"

    def capture_app(application: object, **_options: object) -> None:
        started.append(application)

    monkeypatch.setattr("uvicorn.run", capture_app)
    result = CliRunner().invoke(
        app,
        ["web", "--db", str(tmp_path / "browser.db")],
        env={
            "AGENTBOARD_OWNER_PASSWORD_HASH": "hash",
            "AGENTBOARD_SESSION_SECRET": secret,
        },
    )

    assert result.exit_code == 0
    assert len(started) == 1
    assert started[0].state.web_settings.authentication_enabled is True
    assert started[0].state.web_settings.session_secret == secret


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
