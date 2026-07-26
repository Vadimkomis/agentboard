"""Instance-scoped async SQLite engine and session management."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import event
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from agentboard.infrastructure.paths import resolve_database_path

if TYPE_CHECKING:
    from agentboard.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

DEFAULT_BUSY_TIMEOUT_MS = 5_000


class Database:
    """Own one browser-v0 engine and its session factory."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
        echo: bool = False,
    ) -> None:
        if busy_timeout_ms <= 0:
            raise ValueError("busy_timeout_ms must be positive")
        self.path = resolve_database_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.busy_timeout_ms = busy_timeout_ms
        self.engine = self._create_engine(echo)
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session without committing application-owned transactions."""
        async with self.session_factory() as session:
            try:
                yield session
            except BaseException:
                await session.rollback()
                raise

    def unit_of_work(self) -> SqlAlchemyUnitOfWork:
        """Create a fresh transaction boundary for one application use case."""
        from agentboard.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

        return SqlAlchemyUnitOfWork(self.session_factory)

    async def dispose(self) -> None:
        """Release all pooled SQLite connections."""
        await self.engine.dispose()

    def _create_engine(self, echo: bool) -> AsyncEngine:
        url = URL.create("sqlite+aiosqlite", database=str(self.path))
        engine = create_async_engine(
            url,
            echo=echo,
            connect_args={
                "check_same_thread": False,
                "timeout": self.busy_timeout_ms / 1_000,
            },
        )
        event.listen(
            engine.sync_engine,
            "connect",
            _configure_sqlite_connection(self.busy_timeout_ms),
        )
        return engine


def _configure_sqlite_connection(busy_timeout_ms: int) -> Any:
    def configure(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        finally:
            cursor.close()

    return configure
