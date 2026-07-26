"""Project application commands."""

from __future__ import annotations

from datetime import datetime

from agentboard.application._support import Clock, persisted_id, require_text, utc_now
from agentboard.application.ports import UnitOfWorkFactory
from agentboard.domain.entities import AuditEvent, Project
from agentboard.domain.errors import DuplicateProjectKeyError


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


def _validate_project(
    key: str, name: str, repository_url: str, default_branch: str
) -> tuple[str, ...]:
    return (
        require_text(key, "Project key"),
        require_text(name, "Project name"),
        require_text(repository_url, "Repository URL"),
        require_text(default_branch, "Default branch"),
    )


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
