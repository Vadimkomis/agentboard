"""Sprint commands and active-Sprint query."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from agentboard.application._support import Clock, persisted_id, require_text, utc_now
from agentboard.application.ports import UnitOfWork, UnitOfWorkFactory
from agentboard.domain.entities import (
    ActiveSprint,
    AuditEvent,
    Feature,
    Project,
    Sprint,
    SprintFeature,
)
from agentboard.domain.enums import SprintState
from agentboard.domain.errors import (
    ActiveSprintExistsError,
    CrossProjectFeatureError,
    DuplicateIdentifiersError,
    FeatureAlreadyInSprintError,
    FeatureNotFoundError,
    FeatureNotInSprintError,
    ProjectNotFoundError,
    SprintNotFoundError,
)
from agentboard.domain.ranking import validate_exact_order
from agentboard.domain.sprints import (
    ensure_feature_is_sprint_eligible,
    ensure_sprint_accepts_features,
    ensure_sprint_is_planned,
    start_sprint,
)


class CreatePlannedSprint:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock = utc_now) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, *, project_id: int, name: str, goal: str | None = None) -> Sprint:
        name = require_text(name, "Sprint name")
        async with self._uow_factory() as uow:
            await _get_project(uow, project_id)
            now = self._clock()
            sprint = await uow.sprints.add(
                Sprint(
                    project_id=project_id,
                    number=await uow.sprints.next_number(project_id),
                    name=name,
                    goal=goal,
                    state=SprintState.planned,
                    starts_at=None,
                    ends_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            await uow.audit_events.add(_sprint_event(sprint, "sprint.created", now))
            await uow.commit()
            return sprint


class AddFeatureToSprint:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock = utc_now) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, *, sprint_id: int, feature_id: int) -> SprintFeature:
        async with self._uow_factory() as uow:
            sprint = await _get_sprint(uow, sprint_id)
            feature = await _get_feature(uow, feature_id)
            _ensure_same_project(sprint, feature)
            ensure_sprint_accepts_features(sprint)
            ensure_feature_is_sprint_eligible(feature)
            if await uow.sprints.has_feature(sprint_id, feature_id):
                raise FeatureAlreadyInSprintError(feature_id)
            membership = SprintFeature(
                sprint_id,
                feature_id,
                await uow.sprints.next_feature_rank(sprint_id),
            )
            await uow.sprints.add_feature(membership)
            await uow.audit_events.add(_membership_event(sprint, feature_id, self._clock()))
            await uow.commit()
            return membership


class ReorderSprintMembership:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock = utc_now) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, *, sprint_id: int, feature_ids: Sequence[int]) -> list[Feature]:
        async with self._uow_factory() as uow:
            sprint = await _get_sprint(uow, sprint_id)
            current = await uow.sprints.list_features(sprint_id)
            await _validate_sprint_order(uow, sprint, current, feature_ids)
            await uow.sprints.reorder_features(sprint_id, feature_ids)
            await uow.audit_events.add(_sprint_reorder_event(sprint, feature_ids, self._clock()))
            await uow.commit()
            return await uow.sprints.list_features(sprint_id)


class StartSprint:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock = utc_now) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, *, sprint_id: int) -> Sprint:
        async with self._uow_factory() as uow:
            sprint = await _get_sprint(uow, sprint_id)
            ensure_sprint_is_planned(sprint)
            if await uow.sprints.get_active(sprint.project_id) is not None:
                raise ActiveSprintExistsError(sprint.project_id)
            for feature in await uow.sprints.list_features(sprint_id):
                _ensure_same_project(sprint, feature)
                ensure_feature_is_sprint_eligible(feature)
            started_at = self._clock()
            start_sprint(sprint, started_at)
            await uow.sprints.update(sprint)
            await uow.audit_events.add(_sprint_event(sprint, "sprint.started", started_at))
            await uow.commit()
            return sprint


class GetActiveSprint:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, *, project_id: int) -> ActiveSprint | None:
        async with self._uow_factory() as uow:
            await _get_project(uow, project_id)
            sprint = await uow.sprints.get_active(project_id)
            if sprint is None:
                return None
            features = await uow.sprints.list_features(persisted_id(sprint.id))
            return ActiveSprint(sprint=sprint, features=tuple(features))


async def _get_project(uow: UnitOfWork, project_id: int) -> Project:
    project = await uow.projects.get(project_id)
    if project is None:
        raise ProjectNotFoundError(project_id)
    return project


async def _get_sprint(uow: UnitOfWork, sprint_id: int) -> Sprint:
    sprint = await uow.sprints.get(sprint_id)
    if sprint is None:
        raise SprintNotFoundError(sprint_id)
    return sprint


async def _get_feature(uow: UnitOfWork, feature_id: int) -> Feature:
    feature = await uow.features.get(feature_id)
    if feature is None:
        raise FeatureNotFoundError(feature_id)
    return feature


def _ensure_same_project(sprint: Sprint, feature: Feature) -> None:
    if sprint.project_id != feature.project_id:
        raise CrossProjectFeatureError(persisted_id(feature.id))


async def _validate_sprint_order(
    uow: UnitOfWork,
    sprint: Sprint,
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
        if feature.project_id != sprint.project_id:
            raise CrossProjectFeatureError(feature_id)
        raise FeatureNotInSprintError(feature_id)
    validate_exact_order(current_ids, requested)


def _sprint_event(sprint: Sprint, event_type: str, created_at: datetime) -> AuditEvent:
    sprint_id = persisted_id(sprint.id)
    return AuditEvent(
        project_id=sprint.project_id,
        event_type=event_type,
        payload={"sprint_id": sprint_id, "number": sprint.number},
        created_at=created_at,
    )


def _membership_event(sprint: Sprint, feature_id: int, created_at: datetime) -> AuditEvent:
    return AuditEvent(
        project_id=sprint.project_id,
        feature_id=feature_id,
        event_type="sprint.feature_added",
        payload={"sprint_id": persisted_id(sprint.id), "feature_id": feature_id},
        created_at=created_at,
    )


def _sprint_reorder_event(
    sprint: Sprint,
    feature_ids: Sequence[int],
    created_at: datetime,
) -> AuditEvent:
    return AuditEvent(
        project_id=sprint.project_id,
        event_type="sprint.reordered",
        payload={"sprint_id": persisted_id(sprint.id), "feature_ids": list(feature_ids)},
        created_at=created_at,
    )
