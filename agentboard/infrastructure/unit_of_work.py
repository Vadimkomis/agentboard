"""SQLAlchemy transaction boundary for browser-v0 application handlers."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentboard.infrastructure.conflicts import raise_write_conflict
from agentboard.infrastructure.repositories import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyFeatureRepository,
    SqlAlchemyProjectRepository,
    SqlAlchemySprintRepository,
)


class SqlAlchemyUnitOfWork:
    """Own one session and expose repositories sharing its transaction."""

    projects: SqlAlchemyProjectRepository
    features: SqlAlchemyFeatureRepository
    sprints: SqlAlchemySprintRepository
    audit_events: SqlAlchemyAuditEventRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> SqlAlchemyUnitOfWork:
        if self._session is not None:
            raise RuntimeError("A unit of work cannot be entered twice.")
        self._session = self._session_factory()
        self.projects = SqlAlchemyProjectRepository(self._session)
        self.features = SqlAlchemyFeatureRepository(self._session)
        self.sprints = SqlAlchemySprintRepository(self._session)
        self.audit_events = SqlAlchemyAuditEventRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        session = self._require_session()
        try:
            if session.in_transaction():
                await session.rollback()
        finally:
            await session.close()
            self._session = None

    async def flush(self) -> None:
        try:
            await self._require_session().flush()
        except (IntegrityError, OperationalError) as error:
            raise_write_conflict(error)

    async def commit(self) -> None:
        try:
            await self._require_session().commit()
        except (IntegrityError, OperationalError) as error:
            await self._require_session().rollback()
            raise_write_conflict(error)

    async def rollback(self) -> None:
        await self._require_session().rollback()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("The unit of work must be entered before use.")
        return self._session
