"""Platform-appropriate paths for the browser-v0 application data."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

_APPLICATION_DIRECTORY = "agentboard"
_MACOS_APPLICATION_DIRECTORY = "AgentBoard"
_DATABASE_FILENAME = "agentboard.db"


def default_data_directory(
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the native per-user data directory on supported hosts."""
    host_platform = platform or sys.platform
    environment = os.environ if environ is None else environ
    home_directory = Path.home() if home is None else home

    if host_platform == "darwin":
        return home_directory / "Library" / "Application Support" / _MACOS_APPLICATION_DIRECTORY
    if host_platform.startswith("linux"):
        return _linux_data_directory(environment, home_directory)
    raise RuntimeError(f"AgentBoard supports macOS and Linux, not {host_platform!r}")


def default_database_path(
    *,
    platform: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the default file-backed SQLite database path."""
    return (
        default_data_directory(platform=platform, environ=environ, home=home) / _DATABASE_FILENAME
    )


def resolve_database_path(path: str | Path | None = None) -> Path:
    """Resolve an explicit override or the platform default to an absolute path."""
    selected_path = default_database_path() if path is None else Path(path)
    return selected_path.expanduser().resolve(strict=False)


def _linux_data_directory(environment: Mapping[str, str], home: Path) -> Path:
    configured_directory = environment.get("XDG_DATA_HOME")
    if configured_directory:
        xdg_directory = Path(configured_directory).expanduser()
        if not xdg_directory.is_absolute():
            raise ValueError("XDG_DATA_HOME must be an absolute path")
        return xdg_directory / _APPLICATION_DIRECTORY
    return home / ".local" / "share" / _APPLICATION_DIRECTORY
