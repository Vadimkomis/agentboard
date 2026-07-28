"""Programmatic Alembic migration entry points."""

from __future__ import annotations

import asyncio
from functools import partial
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL

from agentboard.infrastructure.paths import resolve_database_path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_CONFIG_PATH = _PROJECT_ROOT / "alembic.ini"
_MIGRATIONS_PATH = Path(__file__).resolve().parents[1] / "migrations"


def upgrade_database(path: str | Path, revision: str = "head") -> None:
    """Upgrade one file-backed database without starting a nested event loop."""
    database_path = _prepare_database_path(path)
    command.upgrade(_migration_config(database_path), revision)


async def upgrade_database_async(path: str | Path, revision: str = "head") -> None:
    """Run an upgrade off the current event-loop thread."""
    await asyncio.to_thread(partial(upgrade_database, path, revision))


def downgrade_database(path: str | Path, revision: str = "base") -> None:
    """Downgrade one file-backed database without global Alembic state."""
    database_path = _prepare_database_path(path)
    command.downgrade(_migration_config(database_path), revision)


async def downgrade_database_async(path: str | Path, revision: str = "base") -> None:
    """Run a downgrade off the current event-loop thread."""
    await asyncio.to_thread(partial(downgrade_database, path, revision))


def _prepare_database_path(path: str | Path) -> Path:
    database_path = resolve_database_path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return database_path


def _migration_config(database_path: Path) -> Config:
    # Programmatic migrations must also work from an installed wheel, where the
    # repository-root alembic.ini is not present.
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS_PATH))
    url = URL.create("sqlite", database=str(database_path)).render_as_string(hide_password=False)
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config
