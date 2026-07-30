"""Project-scoped read models for the browser presentation layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agentboard.application._support import persisted_id
from agentboard.application.ports import UnitOfWork, UnitOfWorkFactory
from agentboard.domain.entities import ActiveSprint, AuditEvent, Feature, Project, Sprint
from agentboard.domain.enums import EngineeringState, PlanningStage
from agentboard.domain.errors import FeatureNotFoundError, ProjectNotFoundError

ApprovalKind = Literal["design", "pull_request"]


@dataclass(frozen=True, slots=True)
class ProjectWorkspace:
    project: Project
    active_sprint: ActiveSprint | None
    future_backlog: tuple[Feature, ...]


@dataclass(frozen=True, slots=True)
class ProjectFeature:
    project: Project
    feature: Feature
    sprint: Sprint | None
    history: tuple[AuditEvent, ...]


@dataclass(frozen=True, slots=True)
class PendingApproval:
    kind: ApprovalKind
    feature: Feature
    subject_revision: str | None
    actionable: bool


@dataclass(frozen=True, slots=True)
class ProjectReport:
    sprint: Sprint
    features: tuple[Feature, ...]


def presented_engineering_state(
    feature: Feature,
    *,
    in_active_sprint: bool,
) -> EngineeringState | None:
    """Derive only the no-PR presentation state supported by current durable facts."""

    if feature.completed_at is not None or feature.engineering_state is EngineeringState.done:
        return EngineeringState.done
    if feature.engineering_state is not None:
        return feature.engineering_state
    if in_active_sprint and feature.has_approved_design:
        return EngineeringState.ready_for_engineering
    return None


class GetProjectWorkspace:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, *, project_key: str) -> ProjectWorkspace:
        async with self._uow_factory() as uow:
            project = await _get_project_by_key(uow, project_key)
            project_id = persisted_id(project.id)
            sprint = await uow.sprints.get_active(project_id)
            active_sprint = await _active_sprint(uow, sprint)
            return ProjectWorkspace(
                project=project,
                active_sprint=active_sprint,
                future_backlog=tuple(await uow.features.list_future_backlog(project_id)),
            )


class GetProjectFeature:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, *, project_key: str, feature_number: int) -> ProjectFeature:
        async with self._uow_factory() as uow:
            project = await _get_project_by_key(uow, project_key)
            project_id = persisted_id(project.id)
            feature = await uow.features.get_by_project_number(project_id, feature_number)
            if feature is None:
                raise FeatureNotFoundError(feature_number)
            feature_id = persisted_id(feature.id)
            return ProjectFeature(
                project=project,
                feature=feature,
                sprint=await uow.sprints.get_latest_for_feature(project_id, feature_id),
                history=tuple(await uow.audit_events.list_for_feature(project_id, feature_id)),
            )


class ListProjectApprovals:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, *, project_key: str) -> list[PendingApproval]:
        async with self._uow_factory() as uow:
            project = await _get_project_by_key(uow, project_key)
            features = await uow.features.list_for_project(persisted_id(project.id))
            return [approval for feature in features for approval in _pending_approvals(feature)]


class ListProjectReports:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, *, project_key: str) -> list[ProjectReport]:
        async with self._uow_factory() as uow:
            project = await _get_project_by_key(uow, project_key)
            sprints = await uow.sprints.list_completed(persisted_id(project.id))
            return [
                ProjectReport(
                    sprint=sprint,
                    features=tuple(
                        feature
                        for feature in await uow.sprints.list_features(persisted_id(sprint.id))
                        if _completed_in_sprint(feature, sprint)
                    ),
                )
                for sprint in sprints
            ]


async def _get_project_by_key(uow: UnitOfWork, project_key: str) -> Project:
    project = await uow.projects.get_by_key(project_key)
    if project is None:
        raise ProjectNotFoundError(project_key)
    return project


async def _active_sprint(uow: UnitOfWork, sprint: Sprint | None) -> ActiveSprint | None:
    if sprint is None:
        return None
    features = await uow.sprints.list_features(persisted_id(sprint.id))
    return ActiveSprint(sprint=sprint, features=tuple(features))


def _pending_approvals(feature: Feature) -> tuple[PendingApproval, ...]:
    if feature.completed_at is not None or feature.engineering_state is EngineeringState.done:
        return ()
    approvals: list[PendingApproval] = []
    if feature.planning_stage is PlanningStage.design_review and not feature.has_approved_design:
        approvals.append(PendingApproval("design", feature, None, False))
    if feature.engineering_state is EngineeringState.human_review:
        approvals.append(PendingApproval("pull_request", feature, None, False))
    return tuple(approvals)


def _completed_in_sprint(feature: Feature, sprint: Sprint) -> bool:
    completed_at = feature.completed_at
    if completed_at is None or sprint.ends_at is None:
        return False
    return (sprint.starts_at is None or completed_at >= sprint.starts_at) and (
        completed_at <= sprint.ends_at
    )
