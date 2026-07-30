"""Atomic representative data for local browser evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from agentboard.application._support import Clock, persisted_id, utc_now
from agentboard.application.ports import UnitOfWork, UnitOfWorkFactory
from agentboard.domain.entities import (
    AuditEvent,
    Feature,
    Project,
    Sprint,
    SprintFeature,
)
from agentboard.domain.enums import EngineeringState, PlanningStage, SprintState
from agentboard.domain.errors import DuplicateProjectKeyError

DEMO_PROJECT_KEY = "DEMO"


@dataclass(frozen=True, slots=True)
class _FeatureSpec:
    title: str
    description: str
    planning_stage: PlanningStage
    priority: str
    estimate: int | None
    owner: str | None
    approved_design_hash: str | None
    engineering_state: EngineeringState | None = None
    completed_ago: timedelta | None = None


_FEATURE_SPECS = (
    _FeatureSpec(
        "Ship project foundation",
        "Preserve the durable Project, Feature, Sprint, and audit foundation.",
        PlanningStage.design_review,
        "high",
        5,
        "Alex",
        "demo-design-foundation",
        EngineeringState.done,
        timedelta(days=14),
    ),
    _FeatureSpec(
        "Prepare browser workspace",
        "Exercise the initial Ready for Engineering presentation.",
        PlanningStage.design_review,
        "highest",
        3,
        "Sam",
        "demo-design-workspace",
    ),
    _FeatureSpec(
        "Implement activity timeline",
        "Show representative implementation work in progress.",
        PlanningStage.design_review,
        "high",
        5,
        "Jordan",
        "demo-design-timeline",
        EngineeringState.working,
    ),
    _FeatureSpec(
        "Review accessibility polish",
        "Verify keyboard, contrast, and responsive interaction details.",
        PlanningStage.design_review,
        "high",
        3,
        "Taylor",
        "demo-design-accessibility",
        EngineeringState.in_review,
    ),
    _FeatureSpec(
        "Approve release candidate",
        "Represent a candidate waiting for explicit human attention.",
        PlanningStage.design_review,
        "highest",
        2,
        "Morgan",
        "demo-design-release",
        EngineeringState.human_review,
    ),
    _FeatureSpec(
        "Merge demo delivery",
        "Show validated work waiting for its final merge action.",
        PlanningStage.design_review,
        "medium",
        1,
        "Riley",
        "demo-design-merge",
        EngineeringState.ready_to_merge,
    ),
    _FeatureSpec(
        "Publish seeded workspace",
        "Keep completed Current Sprint work visible in Done.",
        PlanningStage.design_review,
        "medium",
        2,
        "Casey",
        "demo-design-publish",
        EngineeringState.done,
        timedelta(hours=1),
    ),
    _FeatureSpec(
        "Define notification preferences",
        "Provide future work that still needs design approval.",
        PlanningStage.design_review,
        "high",
        3,
        None,
        None,
    ),
    _FeatureSpec(
        "Add team workload forecast",
        "Provide a second ranked future-backlog item.",
        PlanningStage.design,
        "medium",
        5,
        "Jamie",
        None,
    ),
    _FeatureSpec(
        "Document release checklist",
        "Provide approved future work that is ready for sprint planning.",
        PlanningStage.evals,
        "low",
        2,
        "Avery",
        "demo-design-checklist",
    ),
)


class SeedDemoWorkspace:
    """Create one complete demo Project without altering existing Projects."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock = utc_now) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self) -> Project:
        async with self._uow_factory() as uow:
            if await uow.projects.get_by_key(DEMO_PROJECT_KEY) is not None:
                raise DuplicateProjectKeyError(DEMO_PROJECT_KEY)
            now = self._clock()
            project = await uow.projects.add(_demo_project(now))
            project_id = persisted_id(project.id)
            await _record_project_event(uow, project, now)
            features = await _add_features(uow, project_id, now)
            await _add_sprints(uow, project_id, features, now)
            await uow.commit()
            return project


def _demo_project(now: datetime) -> Project:
    return Project(
        key=DEMO_PROJECT_KEY,
        name="AgentBoard Demo",
        repository_url="https://github.com/example/agentboard-demo",
        default_branch="main",
        created_at=now - timedelta(days=30),
        updated_at=now,
    )


async def _add_features(
    uow: UnitOfWork,
    project_id: int,
    now: datetime,
) -> dict[int, Feature]:
    features: dict[int, Feature] = {}
    for number, spec in enumerate(_FEATURE_SPECS, start=1):
        completed_at = None if spec.completed_ago is None else now - spec.completed_ago
        feature = await uow.features.add(
            Feature(
                project_id=project_id,
                number=number,
                title=spec.title,
                description=spec.description,
                rank=number,
                planning_stage=spec.planning_stage,
                priority=spec.priority,
                estimate=spec.estimate,
                owner=spec.owner,
                approved_design_hash=spec.approved_design_hash,
                completed_at=completed_at,
                created_at=now - timedelta(days=28),
                updated_at=completed_at or now,
                engineering_state=spec.engineering_state,
            )
        )
        features[number] = feature
        await _record_feature_event(uow, feature)
    return features


async def _add_sprints(
    uow: UnitOfWork,
    project_id: int,
    features: dict[int, Feature],
    now: datetime,
) -> None:
    completed = await uow.sprints.add(_completed_sprint(project_id, now))
    active = await uow.sprints.add(_active_sprint(project_id, now))
    await _record_sprint_event(uow, completed, now - timedelta(days=14))
    await _record_sprint_event(uow, active, now - timedelta(days=2))
    await _add_memberships(uow, completed, features, (1,))
    await _add_memberships(uow, active, features, (2, 3, 4, 5, 6, 7))


def _completed_sprint(project_id: int, now: datetime) -> Sprint:
    return Sprint(
        project_id=project_id,
        number=1,
        name="Sprint 1",
        goal="Establish the durable browser foundation",
        state=SprintState.completed,
        starts_at=now - timedelta(days=21),
        ends_at=now - timedelta(days=14),
        created_at=now - timedelta(days=22),
        updated_at=now - timedelta(days=14),
    )


def _active_sprint(project_id: int, now: datetime) -> Sprint:
    return Sprint(
        project_id=project_id,
        number=2,
        name="Sprint 2",
        goal="Dogfood the complete browser workflow",
        state=SprintState.active,
        starts_at=now - timedelta(days=2),
        ends_at=None,
        created_at=now - timedelta(days=7),
        updated_at=now - timedelta(days=2),
    )


async def _add_memberships(
    uow: UnitOfWork,
    sprint: Sprint,
    features: dict[int, Feature],
    feature_numbers: tuple[int, ...],
) -> None:
    sprint_id = persisted_id(sprint.id)
    for rank, number in enumerate(feature_numbers, start=1):
        feature_id = persisted_id(features[number].id)
        await uow.sprints.add_feature(SprintFeature(sprint_id, feature_id, rank))
        await uow.audit_events.add(
            AuditEvent(
                project_id=sprint.project_id,
                feature_id=feature_id,
                event_type="sprint.feature_added",
                payload={"sprint_id": sprint_id, "feature_id": feature_id},
                created_at=sprint.updated_at,
            )
        )


async def _record_project_event(
    uow: UnitOfWork,
    project: Project,
    now: datetime,
) -> None:
    project_id = persisted_id(project.id)
    await uow.audit_events.add(
        AuditEvent(
            project_id=project_id,
            event_type="project.demo_seeded",
            payload={"project_id": project_id, "key": project.key},
            created_at=now,
        )
    )


async def _record_feature_event(uow: UnitOfWork, feature: Feature) -> None:
    feature_id = persisted_id(feature.id)
    await uow.audit_events.add(
        AuditEvent(
            project_id=feature.project_id,
            feature_id=feature_id,
            event_type="feature.created",
            payload={"feature_id": feature_id, "number": feature.number, "rank": feature.rank},
            created_at=feature.created_at,
        )
    )


async def _record_sprint_event(
    uow: UnitOfWork,
    sprint: Sprint,
    occurred_at: datetime,
) -> None:
    sprint_id = persisted_id(sprint.id)
    await uow.audit_events.add(
        AuditEvent(
            project_id=sprint.project_id,
            event_type="sprint.demo_seeded",
            payload={"sprint_id": sprint_id, "number": sprint.number},
            created_at=occurred_at,
        )
    )
