"""Command-line entry points for the local AgentBoard browser application."""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    from agentboard.domain.entities import Project

app = typer.Typer(
    name="agentboard",
    help="Local project, backlog, and Sprint workspace",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def version() -> None:
    """Print AgentBoard version."""
    from agentboard import __version__

    typer.echo(f"agentboard {__version__}")


@app.command("create-project")
def create_project(
    key: Annotated[str, typer.Argument(help="Stable URL-safe project key")],
    name: Annotated[str, typer.Argument(help="Project display name")],
    repository_url: Annotated[str, typer.Argument(help="Git repository URL")],
    default_branch: Annotated[
        str,
        typer.Option("--default-branch", help="Repository default branch"),
    ] = "main",
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Browser-v0 SQLite path"),
    ] = None,
) -> None:
    """Create a Project that can be opened in the browser UI."""
    from agentboard.domain.errors import DomainError
    from agentboard.infrastructure.migrations import upgrade_database
    from agentboard.infrastructure.paths import resolve_database_path

    database_path = resolve_database_path(db)
    upgrade_database(database_path)
    try:
        project = asyncio.run(
            _create_browser_project(
                database_path,
                key,
                name,
                repository_url,
                default_branch,
            )
        )
    except DomainError as error:
        typer.echo(error.user_message, err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Created {project.key} ({project.name}) in {database_path}")


@app.command("seed-demo")
def seed_demo(
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Browser-v0 SQLite path"),
    ] = None,
) -> None:
    """Create representative data for local browser testing."""
    from agentboard.domain.errors import DomainError
    from agentboard.infrastructure.migrations import upgrade_database
    from agentboard.infrastructure.paths import resolve_database_path

    database_path = resolve_database_path(db)
    upgrade_database(database_path)
    try:
        project = asyncio.run(_seed_browser_demo(database_path))
    except DomainError as error:
        typer.echo(error.user_message, err=True)
        raise typer.Exit(1) from error
    typer.echo(
        f"Created {project.key} ({project.name}) with sample browser data in {database_path}"
    )


async def _create_browser_project(
    database_path: Path,
    key: str,
    name: str,
    repository_url: str,
    default_branch: str,
) -> Project:
    from agentboard.application import CreateProject
    from agentboard.infrastructure.database import Database

    database = Database(database_path)
    try:
        return await CreateProject(database.unit_of_work)(
            key=key,
            name=name,
            repository_url=repository_url,
            default_branch=default_branch,
        )
    finally:
        await database.dispose()


async def _seed_browser_demo(database_path: Path) -> Project:
    from agentboard.application import SeedDemoWorkspace
    from agentboard.infrastructure.database import Database

    database = Database(database_path)
    try:
        return await SeedDemoWorkspace(database.unit_of_work)()
    finally:
        await database.dispose()


@app.command("web")
def web(
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Browser-v0 SQLite path"),
    ] = None,
    host: Annotated[
        str,
        typer.Option("--host", help="Listen address; loopback is the secure default"),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option("--port", min=1, max=65_535),
    ] = 8000,
    session_secret: Annotated[
        str | None,
        typer.Option(
            "--session-secret",
            envvar="AGENTBOARD_SESSION_SECRET",
            help="Optional persistent session secret of at least 32 characters",
        ),
    ] = None,
    secure_cookies: Annotated[
        bool,
        typer.Option("--secure-cookies", help="Require HTTPS for the session cookie"),
    ] = False,
) -> None:
    """Launch the local browser application."""
    if host not in {"127.0.0.1", "localhost"}:
        typer.echo(
            "Only 127.0.0.1 or localhost binding is supported in v0. Keep the "
            "loopback default and connect through an SSH tunnel or trusted private proxy.",
            err=True,
        )
        raise typer.Exit(2)
    from uvicorn import run

    from agentboard.infrastructure.paths import resolve_database_path
    from agentboard.web import WebSettings, create_app

    settings = WebSettings(
        database_path=resolve_database_path(db),
        session_secret=session_secret or secrets.token_urlsafe(32),
        allowed_hosts=("localhost", "127.0.0.1"),
        secure_cookies=secure_cookies,
    )
    run(create_app(settings), host=host, port=port, workers=1)


if __name__ == "__main__":
    app()
