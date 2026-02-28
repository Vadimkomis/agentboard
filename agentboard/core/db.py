"""SQLite async database engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from agentboard.core.models import Base

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

DEFAULT_DB_PATH = Path.home() / ".agentboard" / "agentboard.db"


def get_db_url(db_path: Path | None = None) -> str:
    path = db_path or DEFAULT_DB_PATH
    return f"sqlite+aiosqlite:///{path}"


async def init_db(db_path: Path | None = None) -> None:
    """Initialize engine, create tables, set module-level state."""
    global _engine, _session_factory
    url = get_db_url(db_path)
    db_file = Path(db_path or DEFAULT_DB_PATH)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    _engine = create_async_engine(
        url,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager that yields a database session."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized — call init_db() first")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Database not initialized — call init_db() first")
    return _engine
