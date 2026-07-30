"""Persistence abstractions used by browser-v0 application handlers."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from types import TracebackType
from typing import Protocol, Self, TypeAlias

from agentboard.domain.entities import (
    AuditEvent,
    CommandReceipt,
    Feature,
    Project,
    Sprint,
    SprintFeature,
)


class ProjectRepository(Protocol):
    async def get(self, project_id: int) -> Project | None: ...

    async def get_by_key(self, key: str) -> Project | None: ...

    async def list(self) -> list[Project]: ...

    async def add(self, project: Project) -> Project: ...

    async def delete(self, project_id: int) -> bool: ...

    async def increment_version(
        self,
        project_id: int,
        expected_version: int,
    ) -> int | None: ...


class FeatureRepository(Protocol):
    async def get(self, feature_id: int) -> Feature | None: ...

    async def get_by_project_number(
        self,
        project_id: int,
        feature_number: int,
    ) -> Feature | None: ...

    async def list_for_project(self, project_id: int) -> list[Feature]: ...

    async def list_by_ids(
        self,
        project_id: int,
        feature_ids: Sequence[int],
    ) -> list[Feature]: ...

    async def list_future_backlog(self, project_id: int) -> list[Feature]: ...

    async def next_number(self, project_id: int) -> int: ...

    async def next_rank(self, project_id: int) -> int: ...

    async def add(self, feature: Feature) -> Feature: ...

    async def reorder_future_backlog(
        self,
        project_id: int,
        ordered_ids: Sequence[int],
    ) -> None: ...


class SprintRepository(Protocol):
    async def get(self, sprint_id: int) -> Sprint | None: ...

    async def get_active(self, project_id: int) -> Sprint | None: ...

    async def get_latest_for_feature(
        self,
        project_id: int,
        feature_id: int,
    ) -> Sprint | None: ...

    async def list_completed(self, project_id: int) -> list[Sprint]: ...

    async def next_number(self, project_id: int) -> int: ...

    async def add(self, sprint: Sprint) -> Sprint: ...

    async def update(self, sprint: Sprint) -> None: ...

    async def has_feature(self, sprint_id: int, feature_id: int) -> bool: ...

    async def next_feature_rank(self, sprint_id: int) -> int: ...

    async def add_feature(self, membership: SprintFeature) -> None: ...

    async def list_features(self, sprint_id: int) -> list[Feature]: ...

    async def reorder_features(self, sprint_id: int, ordered_ids: Sequence[int]) -> None: ...


class AuditEventRepository(Protocol):
    async def add(self, event: AuditEvent) -> AuditEvent: ...

    async def list_for_feature(
        self,
        project_id: int,
        feature_id: int,
    ) -> list[AuditEvent]: ...


class CommandReceiptRepository(Protocol):
    async def get(
        self,
        project_id: int,
        idempotency_key: str,
    ) -> CommandReceipt | None: ...

    async def add(self, receipt: CommandReceipt) -> CommandReceipt: ...


class UnitOfWork(Protocol):
    projects: ProjectRepository
    features: FeatureRepository
    sprints: SprintRepository
    audit_events: AuditEventRepository
    command_receipts: CommandReceiptRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def flush(self) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


UnitOfWorkFactory: TypeAlias = Callable[[], UnitOfWork]
