"""Ranked Project backlog commands and queries."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from agentboard.application._support import Clock, persisted_id, utc_now
from agentboard.application.ports import UnitOfWork, UnitOfWorkFactory
from agentboard.domain.entities import AuditEvent, Feature
from agentboard.domain.errors import (
    CrossProjectFeatureError,
    DuplicateIdentifiersError,
    FeatureNotFoundError,
    ProjectNotFoundError,
)
from agentboard.domain.ranking import validate_exact_order


class ListProjectBacklog:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, *, project_id: int) -> list[Feature]:
        async with self._uow_factory() as uow:
            if await uow.projects.get(project_id) is None:
                raise ProjectNotFoundError(project_id)
            return await uow.features.list_future_backlog(project_id)


class ReorderProjectBacklog:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock = utc_now) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, *, project_id: int, feature_ids: Sequence[int]) -> list[Feature]:
        async with self._uow_factory() as uow:
            await _ensure_project(uow, project_id)
            current = await uow.features.list_future_backlog(project_id)
            await _validate_requested_features(uow, project_id, current, feature_ids)
            await uow.features.reorder_future_backlog(project_id, feature_ids)
            await uow.audit_events.add(_reorder_event(project_id, feature_ids, self._clock()))
            await uow.commit()
            return await uow.features.list_future_backlog(project_id)


async def _ensure_project(uow: UnitOfWork, project_id: int) -> None:
    if await uow.projects.get(project_id) is None:
        raise ProjectNotFoundError(project_id)


async def _validate_requested_features(
    uow: UnitOfWork,
    project_id: int,
    current: Sequence[Feature],
    requested: Sequence[int],
) -> None:
    if len(requested) != len(set(requested)):
        raise DuplicateIdentifiersError
    current_ids = [persisted_id(feature.id) for feature in current]
    current_id_set = set(current_ids)
    for feature_id in requested:
        if feature_id in current_id_set:
            continue
        feature = await uow.features.get(feature_id)
        if feature is None:
            raise FeatureNotFoundError(feature_id)
        if feature.project_id != project_id:
            raise CrossProjectFeatureError(feature_id)
    validate_exact_order(current_ids, requested)


def _reorder_event(
    project_id: int,
    feature_ids: Sequence[int],
    created_at: datetime,
) -> AuditEvent:
    return AuditEvent(
        project_id=project_id,
        event_type="backlog.reordered",
        payload={"feature_ids": list(feature_ids)},
        created_at=created_at,
    )
