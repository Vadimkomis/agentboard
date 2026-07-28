"""AgentBoard CLI — entry point for the `agentboard` command.

Commands:
  agentboard start   — Launch the TUI
  agentboard init    — Create default config at ~/.agentboard/config.yml
  agentboard version — Print version
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

if TYPE_CHECKING:
    from agentboard.domain.entities import Project

app = typer.Typer(
    name="agentboard",
    help="Story-driven multi-agent development TUI",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def start(
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to config.yml (default: ~/.agentboard/config.yml)",
        exists=False,
    ),
    db: Path | None = typer.Option(
        None,
        "--db",
        help="Path to SQLite database file (default: ~/.agentboard/agentboard.db)",
    ),
) -> None:
    """Launch the AgentBoard TUI."""
    from agentboard.core.config import Config, load_config, set_config

    cfg = load_config(config)
    if db:
        cfg = Config(
            default_provider=cfg.default_provider,
            claude_cli_path=cfg.claude_cli_path,
            codex_cli_path=cfg.codex_cli_path,
            anthropic_api_key=cfg.anthropic_api_key,
            openai_api_key=cfg.openai_api_key,
            github_token=cfg.github_token,
            agent_config_path=cfg.agent_config_path,
            heartbeat_interval_minutes=cfg.heartbeat_interval_minutes,
            archive_after_days=cfg.archive_after_days,
            workspace_base=cfg.workspace_base,
            db_path=str(db),
        )
    set_config(cfg)

    # Validate that at least one CLI is available
    if not cfg.cli_available("claude") and not cfg.cli_available("codex"):
        typer.echo(
            "Error: Neither claude nor codex CLI found in PATH.\n\n"
            "Install claude CLI:  npm install -g @anthropic-ai/claude-code\n"
            "Install codex CLI:   npm install -g @openai/codex",
            err=True,
        )
        raise typer.Exit(1)

    from agentboard.tui.app import AgentBoardApp

    app_instance = AgentBoardApp(config=cfg)
    app_instance.run()


@app.command()
def init(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing config"),
) -> None:
    """Create default config at ~/.agentboard/config.yml."""
    from agentboard.core.config import CONFIG_PATH, EXAMPLE_CONFIG_PATH, ensure_config_dir

    ensure_config_dir()

    if CONFIG_PATH.exists() and not force:
        typer.echo(f"Config already exists at {CONFIG_PATH}")
        typer.echo("Use --force to overwrite.")
        return

    if EXAMPLE_CONFIG_PATH.exists():
        import shutil

        shutil.copy(EXAMPLE_CONFIG_PATH, CONFIG_PATH)
        typer.echo(f"Config created at {CONFIG_PATH}")
        typer.echo("Edit it to add your GitHub token (optional) and set your preferred provider.")
    else:
        # Write minimal config inline
        CONFIG_PATH.write_text(
            "# AgentBoard configuration\n"
            "# Uses claude/codex CLI — no API keys needed\n\n"
            "default_provider: claude\n"
            "claude_cli_path: claude\n"
            "codex_cli_path: codex\n"
            "heartbeat_interval_minutes: 30\n"
            "archive_after_days: 7\n"
            "\n"
            "# Optional: GitHub token for PR creation\n"
            "# github_token: ghp_...\n"
            "\n"
            "# Optional: override agent configs (from ai-playbook)\n"
            "# agent_config_path: ~/ai-playbook/agents/\n"
        )
        typer.echo(f"Config created at {CONFIG_PATH}")


@app.command()
def version() -> None:
    """Print AgentBoard version."""
    from agentboard import __version__

    typer.echo(f"agentboard {__version__}")


@app.command()
def agents(
    config: Path | None = typer.Option(None, "--config", "-c"),
) -> None:
    """List available agent configurations."""
    from agentboard.core.agent_registry import load_agent_registry
    from agentboard.core.config import load_config

    cfg = load_config(config)
    registry = load_agent_registry(cfg.agent_config_dir if cfg.agent_config_path else None)

    typer.echo(f"{'Name':<15} {'Provider':<10} {'Model':<30} Description")
    typer.echo("-" * 80)
    for name, agent in sorted(registry.items()):
        typer.echo(
            f"{name:<15} {agent.preferred_provider:<10} {agent.model:<30} {agent.description[:40]}"
        )


@app.command("hash-password")
def hash_password() -> None:
    """Generate an owner-password hash for the browser UI."""
    from agentboard.web import hash_owner_password

    password = typer.prompt("Owner password", hide_input=True, confirmation_prompt=True)
    typer.echo(hash_owner_password(password))


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
    owner_password_hash: Annotated[
        str | None,
        typer.Option(
            "--owner-password-hash",
            envvar="AGENTBOARD_OWNER_PASSWORD_HASH",
            help="PBKDF2 hash; prefer the environment variable",
        ),
    ] = None,
    session_secret: Annotated[
        str | None,
        typer.Option(
            "--session-secret",
            envvar="AGENTBOARD_SESSION_SECRET",
            help="At least 32 characters; prefer the environment variable",
        ),
    ] = None,
    secure_cookies: Annotated[
        bool,
        typer.Option("--secure-cookies", help="Require HTTPS for the session cookie"),
    ] = False,
) -> None:
    """Launch the local, owner-authenticated browser application."""
    if host not in {"127.0.0.1", "localhost"}:
        typer.echo(
            "Only 127.0.0.1 or localhost binding is supported in v0. Keep the "
            "loopback default and connect through an SSH tunnel or trusted private proxy.",
            err=True,
        )
        raise typer.Exit(2)
    if owner_password_hash is None or session_secret is None:
        typer.echo(
            "Set AGENTBOARD_OWNER_PASSWORD_HASH and AGENTBOARD_SESSION_SECRET.\n"
            "Generate the password hash with: agentboard hash-password",
            err=True,
        )
        raise typer.Exit(2)
    from uvicorn import run

    from agentboard.infrastructure.paths import resolve_database_path
    from agentboard.web import WebSettings, create_app

    settings = WebSettings(
        database_path=resolve_database_path(db),
        owner_password_hash=owner_password_hash,
        session_secret=session_secret,
        allowed_hosts=("localhost", "127.0.0.1"),
        secure_cookies=secure_cookies,
    )
    run(create_app(settings), host=host, port=port, workers=1)


if __name__ == "__main__":
    app()
