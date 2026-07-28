"""Behavior tests for browser-specific CLI entry points."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentboard.application import (
    GetProjectWorkspace,
    ListProjectApprovals,
    ListProjectReports,
    ListProjects,
)
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


def test_seed_demo_command_populates_every_browser_view(tmp_path: Path) -> None:
    path = tmp_path / "browser.db"
    result = CliRunner().invoke(app, ["seed-demo", "--db", str(path)])

    async def inspect_demo() -> tuple[list[str], list[str], list[str], list[str]]:
        database = Database(path)
        try:
            workspace = await GetProjectWorkspace(database.unit_of_work)(project_key="DEMO")
            approvals = await ListProjectApprovals(database.unit_of_work)(project_key="DEMO")
            reports = await ListProjectReports(database.unit_of_work)(project_key="DEMO")
            active_titles = (
                [feature.title for feature in workspace.active_sprint.features]
                if workspace.active_sprint
                else []
            )
            return (
                [feature.title for feature in workspace.future_backlog],
                active_titles,
                [approval.feature.title for approval in approvals],
                [feature.title for report in reports for feature in report.features],
            )
        finally:
            await database.dispose()

    future, active, approvals, reports = asyncio.run(inspect_demo())

    assert result.exit_code == 0
    assert "Created DEMO (AgentBoard Demo)" in result.stdout
    assert future == [
        "Define notification preferences",
        "Add team workload forecast",
        "Document release checklist",
    ]
    assert "Prepare browser workspace" in active
    assert "Publish seeded workspace" in active
    assert "Define notification preferences" in approvals
    assert "Approve release candidate" in approvals
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


def test_web_command_starts_with_an_ephemeral_csrf_session(
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
    assert len(started[0].state.web_settings.session_secret) >= 32


def test_browser_cli_does_not_expose_password_authentication() -> None:
    root_help = CliRunner().invoke(app, ["--help"])
    web_help = CliRunner().invoke(app, ["web", "--help"])

    assert root_help.exit_code == 0
    assert web_help.exit_code == 0
    assert "hash-password" not in root_help.stdout
    assert "--owner-password-hash" not in web_help.stdout


@pytest.mark.parametrize("host", ["0.0.0.0", "::1"])
def test_web_command_rejects_unsupported_binding(
    host: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("uvicorn.run", lambda *_args, **_kwargs: None)
    result = CliRunner().invoke(
        app,
        ["web", "--host", host],
        env={"AGENTBOARD_SESSION_SECRET": "a-secure-session-secret-that-is-long"},
    )

    assert result.exit_code == 2
    assert "SSH tunnel" in result.stderr
