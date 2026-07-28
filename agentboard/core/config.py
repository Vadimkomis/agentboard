"""Configuration loader for AgentBoard.

Config is stored at ~/.agentboard/config.yml (never committed).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any

yaml: Any = import_module("yaml")

CONFIG_DIR = Path.home() / ".agentboard"
CONFIG_PATH = CONFIG_DIR / "config.yml"
EXAMPLE_CONFIG_PATH = Path(__file__).parent.parent.parent / "config.example.yml"


@dataclass
class Config:
    # LLM providers (CLI path — uses subscription, no API keys needed)
    default_provider: str = "claude"
    claude_cli_path: str = "claude"
    codex_cli_path: str = "codex"

    # Optional: direct API keys for lightweight completion calls (heartbeat, PM refinement)
    # If not set, falls back to CLI subprocess for everything.
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # GitHub (optional — required only for PR creation)
    github_token: str | None = None

    # Agent config path — defaults to bundled defaults if not set
    agent_config_path: str | None = None

    # Behavior
    heartbeat_interval_minutes: int = 30
    archive_after_days: int = 7
    workspace_base: str = "/tmp/agentboard/workspaces"

    # Database
    db_path: str | None = None

    # Resolved at load time — not stored in YAML
    _agent_config_dir: Path = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.agent_config_path:
            self._agent_config_dir = Path(self.agent_config_path).expanduser()
        else:
            # Use bundled defaults
            self._agent_config_dir = Path(__file__).parent.parent / "agents" / "defaults"

    @property
    def agent_config_dir(self) -> Path:
        return self._agent_config_dir

    @property
    def db_file(self) -> Path:
        if self.db_path:
            return Path(self.db_path).expanduser()
        return CONFIG_DIR / "agentboard.db"

    @property
    def workspace_dir(self) -> Path:
        return Path(self.workspace_base)

    def resolve_cli_path(self, provider: str) -> str:
        if provider == "claude":
            return self.claude_cli_path
        if provider == "codex":
            return self.codex_cli_path
        raise ValueError(f"Unknown provider: {provider!r}")

    def cli_available(self, provider: str) -> bool:
        cli = self.resolve_cli_path(provider)
        return shutil.which(cli) is not None


def load_config(config_path: Path | None = None) -> Config:
    """Load config from YAML file, returning defaults if file doesn't exist."""
    path = config_path or CONFIG_PATH
    if not path.exists():
        return Config()

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    # Filter to known fields only
    known = set(Config.__dataclass_fields__)
    filtered = {k: v for k, v in data.items() if k in known}
    return Config(**filtered)


def ensure_config_dir() -> None:
    """Create ~/.agentboard/ if it doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def write_example_config(dest: Path | None = None) -> Path:
    """Copy example config to ~/.agentboard/config.yml (if not already present)."""
    target = dest or CONFIG_PATH
    ensure_config_dir()
    if not target.exists() and EXAMPLE_CONFIG_PATH.exists():
        shutil.copy(EXAMPLE_CONFIG_PATH, target)
    return target


# Module-level singleton — populated by cli.py on startup
_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: Config) -> None:
    global _config
    _config = config
