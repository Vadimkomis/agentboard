"""Alembic environment for the isolated browser-v0 metadata."""

from __future__ import annotations

from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection

from agentboard.infrastructure.orm import BrowserBase
from agentboard.infrastructure.paths import default_database_path

config = context.config
target_metadata = BrowserBase.metadata
BROWSER_TABLE_NAMES = frozenset(target_metadata.tables)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

if not config.get_main_option("sqlalchemy.url"):
    default_path = default_database_path()
    default_path.parent.mkdir(parents=True, exist_ok=True)
    default_url = f"sqlite:///{default_path}"
    config.set_main_option("sqlalchemy.url", default_url.replace("%", "%%"))


def run_migrations_offline() -> None:
    """Configure a SQL-only migration run."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=_include_browser_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations through a synchronous driver, avoiding nested asyncio."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _configure_sqlite(connection)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=_include_browser_object,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


def _configure_sqlite(connection: Connection) -> None:
    connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    connection.exec_driver_sql("PRAGMA busy_timeout=5000")
    connection.commit()


def _include_browser_object(
    _object: Any,
    name: str | None,
    type_: str,
    _reflected: bool,
    _compare_to: Any,
) -> bool:
    return type_ != "table" or name in BROWSER_TABLE_NAMES


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
