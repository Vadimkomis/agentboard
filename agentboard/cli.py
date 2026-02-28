"""AgentBoard CLI — entry point for the `agentboard` command.

Commands:
  agentboard start   — Launch the TUI
  agentboard init    — Create default config at ~/.agentboard/config.yml
  agentboard version — Print version
"""

from __future__ import annotations

from pathlib import Path

import typer

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
        "--config", "-c",
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
        typer.echo(f"{name:<15} {agent.preferred_provider:<10} {agent.model:<30} {agent.description[:40]}")


if __name__ == "__main__":
    app()
