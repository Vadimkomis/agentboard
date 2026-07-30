"""Project application commands."""

from __future__ import annotations

import re
from datetime import datetime

from agentboard.application._support import Clock, persisted_id, require_text, utc_now
from agentboard.application.ports import UnitOfWorkFactory
from agentboard.domain.entities import AuditEvent, Project
from agentboard.domain.errors import (
    DuplicateProjectKeyError,
    InvalidInputError,
    ProjectNotFoundError,
)

_PROJECT_KEY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


class CreateProject:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock = utc_now) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        key: str,
        name: str,
        repository_url: str,
        default_branch: str,
    ) -> Project:
        values = _validate_project(key, name, repository_url, default_branch)
        async with self._uow_factory() as uow:
            if await uow.projects.get_by_key(values[0]) is not None:
                raise DuplicateProjectKeyError(values[0])
            now = self._clock()
            project = await uow.projects.add(_new_project(*values, now=now))
            await uow.audit_events.add(_created_event(project, now))
            await uow.commit()
            return project


class GetProject:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, *, project_id: int) -> Project:
        async with self._uow_factory() as uow:
            project = await uow.projects.get(project_id)
            if project is None:
                raise ProjectNotFoundError(project_id)
            return project


class ListProjects:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self) -> list[Project]:
        async with self._uow_factory() as uow:
            return await uow.projects.list()


class DeleteProject:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(
        self,
        *,
        project_key: str,
        confirmation_key: str,
    ) -> Project:
        if confirmation_key != project_key:
            raise InvalidInputError("Project deletion confirmation did not match.")
        async with self._uow_factory() as uow:
            project = await uow.projects.get_by_key(project_key)
            if project is None:
                raise ProjectNotFoundError(project_key)
            project_id = persisted_id(project.id)
            if not await uow.projects.delete(project_id):
                raise ProjectNotFoundError(project_key)
            await uow.commit()
            return project


def _validate_project(
    key: str, name: str, repository_url: str, default_branch: str
) -> tuple[str, ...]:
    return (
        _validate_project_key(key),
        require_text(name, "Project name"),
        require_text(repository_url, "Repository URL"),
        require_text(default_branch, "Default branch"),
    )


def _validate_project_key(value: str) -> str:
    key = require_text(value, "Project key")
    if len(key) > 64:
        raise InvalidInputError("Project key must contain at most 64 characters.")
    if _PROJECT_KEY_PATTERN.fullmatch(key) is None:
        raise InvalidInputError(
            "Project key may contain only letters, numbers, hyphens, and underscores."
        )
    return key


def _new_project(
    key: str,
    name: str,
    repository_url: str,
    default_branch: str,
    *,
    now: datetime,
) -> Project:
    return Project(key, name, repository_url, default_branch, now, now)


def _created_event(project: Project, created_at: datetime) -> AuditEvent:
    project_id = persisted_id(project.id)
    return AuditEvent(
        project_id=project_id,
        event_type="project.created",
        payload={"project_id": project_id, "key": project.key},
        created_at=created_at,
    )
