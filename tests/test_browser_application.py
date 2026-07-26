"""Deterministic fake-backed tests for browser-v0 application handlers."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from types import TracebackType

import pytest

from agentboard.application import (
    AddFeatureToSprint,
    CreateFeature,
    CreatePlannedSprint,
    CreateProject,
    GetActiveSprint,
    ListProjectBacklog,
    ReorderProjectBacklog,
    ReorderSprintMembership,
    StartSprint,
    _support,
)
from agentboard.domain.entities import AuditEvent, Feature, Project, Sprint, SprintFeature
from agentboard.domain.enums import PlanningStage, SprintState
from agentboard.domain.errors import (
    ActiveSprintExistsError,
    CrossProjectFeatureError,
    DesignApprovalRequiredError,
    DuplicateIdentifiersError,
    DuplicateProjectKeyError,
    FeatureAlreadyInSprintError,
    FeatureNotFoundError,
    FeatureNotInSprintError,
    IncompleteReorderError,
    InvalidInputError,
    ProjectNotFoundError,
    SprintCompletedError,
    SprintNotFoundError,
    SprintNotPlannedError,
)

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def fixed_clock() -> datetime:
    return NOW


class FakeStore:
    def __init__(self) -> None:
        self.projects: dict[int, Project] = {}
        self.features: dict[int, Feature] = {}
        self.sprints: dict[int, Sprint] = {}
        self.memberships: dict[tuple[int, int], SprintFeature] = {}
        self.audit_events: list[AuditEvent] = []


class FakeProjectRepository:
    def __init__(self, uow: FakeUnitOfWork) -> None:
        self._uow = uow

    async def get(self, project_id: int) -> Project | None:
        return self._uow.projects_data.get(project_id)

    async def get_by_key(self, key: str) -> Project | None:
        return next(
            (project for project in self._uow.projects_data.values() if project.key == key),
            None,
        )

    async def add(self, project: Project) -> Project:
        if self._uow.assign_identifiers:
            project.id = _next_identifier(self._uow.projects_data)
        if project.id is not None:
            self._uow.projects_data[project.id] = project
        return project


class FakeFeatureRepository:
    def __init__(self, uow: FakeUnitOfWork) -> None:
        self._uow = uow

    async def get(self, feature_id: int) -> Feature | None:
        return self._uow.features_data.get(feature_id)

    async def list_for_project(self, project_id: int) -> list[Feature]:
        return sorted(
            (
                feature
                for feature in self._uow.features_data.values()
                if feature.project_id == project_id
            ),
            key=lambda feature: feature.rank,
        )

    async def next_number(self, project_id: int) -> int:
        numbers = [
            feature.number
            for feature in self._uow.features_data.values()
            if feature.project_id == project_id
        ]
        return max(numbers, default=0) + 1

    async def next_rank(self, project_id: int) -> int:
        ranks = [
            feature.rank
            for feature in self._uow.features_data.values()
            if feature.project_id == project_id
        ]
        return max(ranks, default=0) + 1

    async def add(self, feature: Feature) -> Feature:
        if self._uow.assign_identifiers:
            feature.id = _next_identifier(self._uow.features_data)
        if feature.id is not None:
            self._uow.features_data[feature.id] = feature
        return feature

    async def reorder(self, project_id: int, ordered_ids: list[int]) -> None:
        for rank, feature_id in enumerate(ordered_ids, start=1):
            self._uow.features_data[feature_id].rank = rank
            if self._uow.fail_backlog_reorder and rank == 1:
                raise RuntimeError("injected backlog reorder failure")


class FakeSprintRepository:
    def __init__(self, uow: FakeUnitOfWork) -> None:
        self._uow = uow

    async def get(self, sprint_id: int) -> Sprint | None:
        return self._uow.sprints_data.get(sprint_id)

    async def get_active(self, project_id: int) -> Sprint | None:
        return next(
            (
                sprint
                for sprint in self._uow.sprints_data.values()
                if sprint.project_id == project_id and sprint.state is SprintState.active
            ),
            None,
        )

    async def next_number(self, project_id: int) -> int:
        numbers = [
            sprint.number
            for sprint in self._uow.sprints_data.values()
            if sprint.project_id == project_id
        ]
        return max(numbers, default=0) + 1

    async def add(self, sprint: Sprint) -> Sprint:
        if self._uow.assign_identifiers:
            sprint.id = _next_identifier(self._uow.sprints_data)
        if sprint.id is not None:
            self._uow.sprints_data[sprint.id] = sprint
        return sprint

    async def update(self, sprint: Sprint) -> None:
        if sprint.id is not None:
            self._uow.sprints_data[sprint.id] = sprint

    async def has_feature(self, sprint_id: int, feature_id: int) -> bool:
        return (sprint_id, feature_id) in self._uow.memberships_data

    async def next_feature_rank(self, sprint_id: int) -> int:
        ranks = [
            membership.sprint_rank
            for membership in self._uow.memberships_data.values()
            if membership.sprint_id == sprint_id
        ]
        return max(ranks, default=0) + 1

    async def add_feature(self, membership: SprintFeature) -> None:
        key = (membership.sprint_id, membership.feature_id)
        self._uow.memberships_data[key] = membership

    async def list_features(self, sprint_id: int) -> list[Feature]:
        memberships = sorted(
            (
                membership
                for membership in self._uow.memberships_data.values()
                if membership.sprint_id == sprint_id
            ),
            key=lambda membership: membership.sprint_rank,
        )
        return [self._uow.features_data[membership.feature_id] for membership in memberships]

    async def reorder_features(self, sprint_id: int, ordered_ids: list[int]) -> None:
        for rank, feature_id in enumerate(ordered_ids, start=1):
            self._uow.memberships_data[(sprint_id, feature_id)].sprint_rank = rank
            if self._uow.fail_sprint_reorder and rank == 1:
                raise RuntimeError("injected Sprint reorder failure")


class FakeAuditEventRepository:
    def __init__(self, uow: FakeUnitOfWork) -> None:
        self._uow = uow

    async def add(self, event: AuditEvent) -> AuditEvent:
        event.id = len(self._uow.audit_data) + 1
        self._uow.audit_data.append(event)
        return event


class FakeUnitOfWork:
    def __init__(
        self,
        store: FakeStore,
        *,
        assign_identifiers: bool,
        fail_commit: bool,
        fail_backlog_reorder: bool,
        fail_sprint_reorder: bool,
    ) -> None:
        self._store = store
        self.assign_identifiers = assign_identifiers
        self.fail_commit = fail_commit
        self.fail_backlog_reorder = fail_backlog_reorder
        self.fail_sprint_reorder = fail_sprint_reorder
        self.projects_data: dict[int, Project] = {}
        self.features_data: dict[int, Feature] = {}
        self.sprints_data: dict[int, Sprint] = {}
        self.memberships_data: dict[tuple[int, int], SprintFeature] = {}
        self.audit_data: list[AuditEvent] = []
        self.projects = FakeProjectRepository(self)
        self.features = FakeFeatureRepository(self)
        self.sprints = FakeSprintRepository(self)
        self.audit_events = FakeAuditEventRepository(self)
        self.committed = False
        self.rolled_back = False
        self.flush_count = 0

    async def __aenter__(self) -> FakeUnitOfWork:
        self.projects_data = deepcopy(self._store.projects)
        self.features_data = deepcopy(self._store.features)
        self.sprints_data = deepcopy(self._store.sprints)
        self.memberships_data = deepcopy(self._store.memberships)
        self.audit_data = deepcopy(self._store.audit_events)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None or not self.committed:
            await self.rollback()

    async def flush(self) -> None:
        self.flush_count += 1

    async def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("injected commit failure")
        self._store.projects = deepcopy(self.projects_data)
        self._store.features = deepcopy(self.features_data)
        self._store.sprints = deepcopy(self.sprints_data)
        self._store.memberships = deepcopy(self.memberships_data)
        self._store.audit_events = deepcopy(self.audit_data)
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeUnitOfWorkFactory:
    def __init__(
        self,
        store: FakeStore | None = None,
        *,
        assign_identifiers: bool = True,
        fail_commit: bool = False,
        fail_backlog_reorder: bool = False,
        fail_sprint_reorder: bool = False,
    ) -> None:
        self.store = store or FakeStore()
        self.assign_identifiers = assign_identifiers
        self.fail_commit = fail_commit
        self.fail_backlog_reorder = fail_backlog_reorder
        self.fail_sprint_reorder = fail_sprint_reorder
        self.instances: list[FakeUnitOfWork] = []

    def __call__(self) -> FakeUnitOfWork:
        uow = FakeUnitOfWork(
            self.store,
            assign_identifiers=self.assign_identifiers,
            fail_commit=self.fail_commit,
            fail_backlog_reorder=self.fail_backlog_reorder,
            fail_sprint_reorder=self.fail_sprint_reorder,
        )
        self.instances.append(uow)
        return uow


def _next_identifier(records: dict[int, object]) -> int:
    return max(records, default=0) + 1


def seed_project(
    store: FakeStore,
    *,
    project_id: int,
    key: str,
) -> Project:
    project = Project(
        id=project_id,
        key=key,
        name=f"Project {key}",
        repository_url=f"https://example.test/{key}.git",
        default_branch="main",
        created_at=NOW,
        updated_at=NOW,
    )
    store.projects[project_id] = project
    return project


def seed_feature(
    store: FakeStore,
    *,
    feature_id: int,
    project_id: int,
    number: int,
    rank: int,
    approval: str | None = "design-sha-1",
    title: str | None = None,
) -> Feature:
    feature = Feature(
        id=feature_id,
        project_id=project_id,
        number=number,
        title=title or f"Feature {feature_id}",
        description=f"Description {feature_id}",
        rank=rank,
        planning_stage=PlanningStage.design_review,
        engineering_state=None,
        priority="medium",
        estimate=3,
        owner="owner@example.test",
        approved_design_hash=approval,
        completed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    store.features[feature_id] = feature
    return feature


def seed_sprint(
    store: FakeStore,
    *,
    sprint_id: int,
    project_id: int,
    number: int,
    state: SprintState = SprintState.planned,
) -> Sprint:
    sprint = Sprint(
        id=sprint_id,
        project_id=project_id,
        number=number,
        name=f"Sprint {sprint_id}",
        goal="Fixed test goal",
        state=state,
        starts_at=NOW if state is SprintState.active else None,
        ends_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    store.sprints[sprint_id] = sprint
    return sprint


def seed_membership(
    store: FakeStore,
    *,
    sprint_id: int,
    feature_id: int,
    rank: int,
) -> SprintFeature:
    membership = SprintFeature(sprint_id=sprint_id, feature_id=feature_id, sprint_rank=rank)
    store.memberships[(sprint_id, feature_id)] = membership
    return membership


def audit_types(store: FakeStore) -> list[str]:
    return [event.event_type for event in store.audit_events]


async def test_create_project_normalizes_values_and_commits_its_audit_event() -> None:
    factory = FakeUnitOfWorkFactory()

    project = await CreateProject(factory, fixed_clock)(
        key="  APP  ",
        name="  AgentBoard  ",
        repository_url="  https://example.test/agentboard.git  ",
        default_branch="  main  ",
    )

    assert project.id == 1
    assert (project.key, project.name) == ("APP", "AgentBoard")
    assert project.repository_url == "https://example.test/agentboard.git"
    assert project.default_branch == "main"
    assert project.created_at == NOW
    assert factory.instances[0].committed is True
    assert audit_types(factory.store) == ["project.created"]
    assert factory.store.audit_events[0].payload == {"project_id": 1, "key": "APP"}


async def test_duplicate_project_key_rolls_back_without_an_audit_event() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="APP")
    factory = FakeUnitOfWorkFactory(store)

    with pytest.raises(DuplicateProjectKeyError) as captured:
        await CreateProject(factory, fixed_clock)(
            key="APP",
            name="Duplicate",
            repository_url="https://example.test/duplicate.git",
            default_branch="main",
        )

    assert captured.value.code == "duplicate_project_key"
    assert len(factory.store.projects) == 1
    assert factory.store.audit_events == []
    assert factory.instances[0].rolled_back is True


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"key": " "}, "Project key"),
        ({"name": ""}, "Project name"),
        ({"repository_url": "\n"}, "Repository URL"),
        ({"default_branch": "\t"}, "Default branch"),
    ],
)
async def test_create_project_rejects_blank_required_text(
    overrides: dict[str, str],
    message: str,
) -> None:
    factory = FakeUnitOfWorkFactory()
    values = {
        "key": "APP",
        "name": "AgentBoard",
        "repository_url": "https://example.test/agentboard.git",
        "default_branch": "main",
    }
    values.update(overrides)

    with pytest.raises(InvalidInputError, match=message):
        await CreateProject(factory, fixed_clock)(**values)

    assert factory.instances == []


async def test_create_project_requires_the_adapter_to_assign_an_identifier() -> None:
    factory = FakeUnitOfWorkFactory(assign_identifiers=False)

    with pytest.raises(RuntimeError, match="did not assign"):
        await CreateProject(factory, fixed_clock)(
            key="APP",
            name="AgentBoard",
            repository_url="https://example.test/agentboard.git",
            default_branch="main",
        )

    assert factory.store.projects == {}
    assert factory.store.audit_events == []


async def test_create_feature_appends_with_independent_project_number_and_rank() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_project(store, project_id=2, key="TWO")
    seed_feature(store, feature_id=1, project_id=1, number=1, rank=1)
    seed_feature(store, feature_id=2, project_id=1, number=2, rank=2)
    seed_feature(store, feature_id=3, project_id=2, number=1, rank=1)
    factory = FakeUnitOfWorkFactory(store)
    handler = CreateFeature(factory, fixed_clock)

    project_one_feature = await handler(
        project_id=1,
        title="  Third in one  ",
        description="Keep project sequences isolated.",
        planning_stage=PlanningStage.spec,
        priority="  high  ",
        estimate=5,
        owner="owner@example.test",
        approved_design_hash="design-sha-3",
    )
    project_two_feature = await handler(
        project_id=2,
        title="Second in two",
        description="Independent sequence.",
    )

    assert (project_one_feature.number, project_one_feature.rank) == (3, 3)
    assert (project_two_feature.number, project_two_feature.rank) == (2, 2)
    assert project_one_feature.title == "Third in one"
    assert project_one_feature.priority == "high"
    assert project_one_feature.planning_stage is PlanningStage.spec
    assert project_one_feature.created_at == NOW
    assert [event.payload["number"] for event in factory.store.audit_events] == [3, 2]


async def test_create_feature_rejects_a_missing_project_without_state_or_audit() -> None:
    factory = FakeUnitOfWorkFactory()

    with pytest.raises(ProjectNotFoundError) as captured:
        await CreateFeature(factory, fixed_clock)(
            project_id=404,
            title="Orphan",
            description="Must not persist",
        )

    assert captured.value.code == "project_not_found"
    assert factory.store.features == {}
    assert factory.store.audit_events == []


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"title": " "}, "Feature title"),
        ({"priority": ""}, "Feature priority"),
        ({"estimate": -1}, "must not be negative"),
    ],
)
async def test_create_feature_rejects_invalid_values(
    kwargs: dict[str, object],
    message: str,
) -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    factory = FakeUnitOfWorkFactory(store)
    values: dict[str, object] = {
        "project_id": 1,
        "title": "Feature",
        "description": "Description",
    }
    values.update(kwargs)

    with pytest.raises(InvalidInputError, match=message):
        await CreateFeature(factory, fixed_clock)(**values)

    assert factory.store.features == {}
    assert factory.store.audit_events == []


async def test_list_project_backlog_is_ranked_and_project_scoped() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_project(store, project_id=2, key="TWO")
    seed_feature(store, feature_id=1, project_id=1, number=1, rank=2)
    seed_feature(store, feature_id=2, project_id=1, number=2, rank=1)
    seed_feature(store, feature_id=3, project_id=2, number=1, rank=1)
    factory = FakeUnitOfWorkFactory(store)

    backlog = await ListProjectBacklog(factory)(project_id=1)

    assert [feature.id for feature in backlog] == [2, 1]
    assert {feature.project_id for feature in backlog} == {1}


async def test_list_project_backlog_rejects_a_missing_project() -> None:
    factory = FakeUnitOfWorkFactory()

    with pytest.raises(ProjectNotFoundError):
        await ListProjectBacklog(factory)(project_id=404)


@pytest.mark.parametrize(
    "requested_ids",
    [
        [2, 3, 1],
        [1, 3, 2],
        [3, 1, 2],
    ],
)
async def test_reorder_backlog_moves_first_middle_and_last_without_other_mutation(
    requested_ids: list[int],
) -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_project(store, project_id=2, key="TWO")
    originals = [
        seed_feature(
            store,
            feature_id=feature_id,
            project_id=1,
            number=feature_id,
            rank=feature_id,
        )
        for feature_id in (1, 2, 3)
    ]
    other = seed_feature(store, feature_id=4, project_id=2, number=1, rank=1)
    original_fields = {
        feature.id: (feature.number, feature.title, feature.project_id) for feature in originals
    }
    factory = FakeUnitOfWorkFactory(store)

    reordered = await ReorderProjectBacklog(factory, fixed_clock)(
        project_id=1,
        feature_ids=requested_ids,
    )

    assert [feature.id for feature in reordered] == requested_ids
    assert [feature.rank for feature in reordered] == [1, 2, 3]
    assert {
        feature.id: (feature.number, feature.title, feature.project_id) for feature in reordered
    } == original_fields
    assert factory.store.features[4] == other
    assert factory.store.audit_events[-1].payload == {"feature_ids": requested_ids}


@pytest.mark.parametrize("requested_ids", [[], [1]])
async def test_reorder_empty_and_single_feature_backlogs(
    requested_ids: list[int],
) -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    if requested_ids:
        seed_feature(store, feature_id=1, project_id=1, number=1, rank=1)
    factory = FakeUnitOfWorkFactory(store)

    reordered = await ReorderProjectBacklog(factory, fixed_clock)(
        project_id=1,
        feature_ids=requested_ids,
    )

    assert [feature.id for feature in reordered] == requested_ids
    assert audit_types(factory.store) == ["backlog.reordered"]


async def test_reorder_backlog_rejects_duplicate_identifiers_atomically() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_feature(store, feature_id=1, project_id=1, number=1, rank=1)
    seed_feature(store, feature_id=2, project_id=1, number=2, rank=2)
    factory = FakeUnitOfWorkFactory(store)

    with pytest.raises(DuplicateIdentifiersError):
        await ReorderProjectBacklog(factory, fixed_clock)(
            project_id=1,
            feature_ids=[1, 1],
        )

    assert [feature.rank for feature in factory.store.features.values()] == [1, 2]
    assert factory.store.audit_events == []


async def test_reorder_backlog_rejects_an_incomplete_order_atomically() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_feature(store, feature_id=1, project_id=1, number=1, rank=1)
    seed_feature(store, feature_id=2, project_id=1, number=2, rank=2)
    factory = FakeUnitOfWorkFactory(store)

    with pytest.raises(IncompleteReorderError):
        await ReorderProjectBacklog(factory, fixed_clock)(
            project_id=1,
            feature_ids=[1],
        )

    assert [feature.rank for feature in factory.store.features.values()] == [1, 2]
    assert factory.store.audit_events == []


async def test_reorder_backlog_distinguishes_unknown_and_cross_project_ids() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_project(store, project_id=2, key="TWO")
    seed_feature(store, feature_id=1, project_id=1, number=1, rank=1)
    seed_feature(store, feature_id=2, project_id=2, number=1, rank=1)
    factory = FakeUnitOfWorkFactory(store)
    handler = ReorderProjectBacklog(factory, fixed_clock)

    with pytest.raises(FeatureNotFoundError):
        await handler(project_id=1, feature_ids=[404])
    with pytest.raises(CrossProjectFeatureError):
        await handler(project_id=1, feature_ids=[2])

    assert factory.store.features[1].rank == 1
    assert factory.store.features[2].rank == 1
    assert factory.store.audit_events == []


async def test_reorder_backlog_rejects_a_missing_project() -> None:
    factory = FakeUnitOfWorkFactory()

    with pytest.raises(ProjectNotFoundError):
        await ReorderProjectBacklog(factory, fixed_clock)(
            project_id=404,
            feature_ids=[],
        )


async def test_repository_failure_rolls_back_partially_applied_backlog_ranks() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_feature(store, feature_id=1, project_id=1, number=1, rank=1)
    seed_feature(store, feature_id=2, project_id=1, number=2, rank=2)
    factory = FakeUnitOfWorkFactory(store, fail_backlog_reorder=True)

    with pytest.raises(RuntimeError, match="injected backlog reorder failure"):
        await ReorderProjectBacklog(factory, fixed_clock)(
            project_id=1,
            feature_ids=[2, 1],
        )

    assert factory.store.features[1].rank == 1
    assert factory.store.features[2].rank == 2
    assert factory.store.audit_events == []
    assert factory.instances[0].rolled_back is True


async def test_create_planned_sprints_number_independently_per_project() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_project(store, project_id=2, key="TWO")
    seed_sprint(store, sprint_id=1, project_id=1, number=1)
    factory = FakeUnitOfWorkFactory(store)
    handler = CreatePlannedSprint(factory, fixed_clock)

    project_one = await handler(project_id=1, name="  Next One  ", goal="Goal one")
    project_two = await handler(project_id=2, name="First Two")

    assert (project_one.number, project_one.state) == (2, SprintState.planned)
    assert (project_two.number, project_two.state) == (1, SprintState.planned)
    assert project_one.name == "Next One"
    assert project_one.starts_at is None
    assert audit_types(factory.store) == ["sprint.created", "sprint.created"]


async def test_create_planned_sprint_rejects_missing_project_and_blank_name() -> None:
    missing_factory = FakeUnitOfWorkFactory()

    with pytest.raises(ProjectNotFoundError):
        await CreatePlannedSprint(missing_factory, fixed_clock)(
            project_id=404,
            name="Sprint",
        )

    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    blank_factory = FakeUnitOfWorkFactory(store)
    with pytest.raises(InvalidInputError, match="Sprint name"):
        await CreatePlannedSprint(blank_factory, fixed_clock)(project_id=1, name=" ")

    assert blank_factory.instances == []
    assert blank_factory.store.sprints == {}


async def test_add_eligible_features_appends_ranked_sprint_membership() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_sprint(store, sprint_id=1, project_id=1, number=1)
    seed_feature(store, feature_id=1, project_id=1, number=1, rank=1)
    seed_feature(store, feature_id=2, project_id=1, number=2, rank=2)
    factory = FakeUnitOfWorkFactory(store)
    handler = AddFeatureToSprint(factory, fixed_clock)

    first = await handler(sprint_id=1, feature_id=1)
    second = await handler(sprint_id=1, feature_id=2)

    assert (first.sprint_rank, second.sprint_rank) == (1, 2)
    assert list(factory.store.memberships) == [(1, 1), (1, 2)]
    assert audit_types(factory.store) == ["sprint.feature_added", "sprint.feature_added"]
    assert factory.store.audit_events[-1].feature_id == 2


async def test_add_feature_to_sprint_rejects_missing_records() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_sprint(store, sprint_id=1, project_id=1, number=1)
    factory = FakeUnitOfWorkFactory(store)
    handler = AddFeatureToSprint(factory, fixed_clock)

    with pytest.raises(SprintNotFoundError):
        await handler(sprint_id=404, feature_id=1)
    with pytest.raises(FeatureNotFoundError):
        await handler(sprint_id=1, feature_id=404)

    assert factory.store.memberships == {}
    assert factory.store.audit_events == []


async def test_add_feature_to_sprint_rejects_cross_project_membership() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_project(store, project_id=2, key="TWO")
    seed_sprint(store, sprint_id=1, project_id=1, number=1)
    seed_feature(store, feature_id=2, project_id=2, number=1, rank=1)
    factory = FakeUnitOfWorkFactory(store)

    with pytest.raises(CrossProjectFeatureError) as captured:
        await AddFeatureToSprint(factory, fixed_clock)(sprint_id=1, feature_id=2)

    assert captured.value.code == "cross_project_feature"
    assert factory.store.memberships == {}
    assert factory.store.audit_events == []


async def test_add_feature_to_sprint_requires_design_approval() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_sprint(store, sprint_id=1, project_id=1, number=1)
    seed_feature(store, feature_id=1, project_id=1, number=1, rank=1, approval=None)
    factory = FakeUnitOfWorkFactory(store)

    with pytest.raises(DesignApprovalRequiredError):
        await AddFeatureToSprint(factory, fixed_clock)(sprint_id=1, feature_id=1)

    assert factory.store.memberships == {}
    assert factory.store.audit_events == []


async def test_add_feature_to_sprint_rejects_completed_and_duplicate_membership() -> None:
    completed_store = FakeStore()
    seed_project(completed_store, project_id=1, key="ONE")
    seed_sprint(
        completed_store,
        sprint_id=1,
        project_id=1,
        number=1,
        state=SprintState.completed,
    )
    seed_feature(completed_store, feature_id=1, project_id=1, number=1, rank=1)
    completed_factory = FakeUnitOfWorkFactory(completed_store)
    with pytest.raises(SprintCompletedError):
        await AddFeatureToSprint(completed_factory, fixed_clock)(sprint_id=1, feature_id=1)

    duplicate_store = FakeStore()
    seed_project(duplicate_store, project_id=1, key="ONE")
    seed_sprint(duplicate_store, sprint_id=1, project_id=1, number=1)
    seed_feature(duplicate_store, feature_id=1, project_id=1, number=1, rank=1)
    seed_membership(duplicate_store, sprint_id=1, feature_id=1, rank=1)
    duplicate_factory = FakeUnitOfWorkFactory(duplicate_store)
    with pytest.raises(FeatureAlreadyInSprintError):
        await AddFeatureToSprint(duplicate_factory, fixed_clock)(sprint_id=1, feature_id=1)

    assert completed_factory.store.memberships == {}
    assert duplicate_factory.store.audit_events == []


@pytest.mark.parametrize(
    "requested_ids",
    [
        [2, 3, 1],
        [1, 3, 2],
        [3, 1, 2],
    ],
)
async def test_reorder_sprint_membership_moves_first_middle_and_last(
    requested_ids: list[int],
) -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_sprint(store, sprint_id=1, project_id=1, number=1)
    for feature_id in (1, 2, 3):
        seed_feature(
            store,
            feature_id=feature_id,
            project_id=1,
            number=feature_id,
            rank=feature_id,
        )
        seed_membership(store, sprint_id=1, feature_id=feature_id, rank=feature_id)
    factory = FakeUnitOfWorkFactory(store)

    reordered = await ReorderSprintMembership(factory, fixed_clock)(
        sprint_id=1,
        feature_ids=requested_ids,
    )

    assert [feature.id for feature in reordered] == requested_ids
    assert [
        factory.store.memberships[(1, feature_id)].sprint_rank for feature_id in requested_ids
    ] == [1, 2, 3]
    assert factory.store.audit_events[-1].payload == {
        "sprint_id": 1,
        "feature_ids": requested_ids,
    }


@pytest.mark.parametrize("requested_ids", [[], [1]])
async def test_reorder_empty_and_single_sprint_membership(
    requested_ids: list[int],
) -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_sprint(store, sprint_id=1, project_id=1, number=1)
    if requested_ids:
        seed_feature(store, feature_id=1, project_id=1, number=1, rank=1)
        seed_membership(store, sprint_id=1, feature_id=1, rank=1)
    factory = FakeUnitOfWorkFactory(store)

    reordered = await ReorderSprintMembership(factory, fixed_clock)(
        sprint_id=1,
        feature_ids=requested_ids,
    )

    assert [feature.id for feature in reordered] == requested_ids
    assert audit_types(factory.store) == ["sprint.reordered"]


async def test_reorder_sprint_membership_rejects_invalid_identifiers_atomically() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_project(store, project_id=2, key="TWO")
    seed_sprint(store, sprint_id=1, project_id=1, number=1)
    seed_feature(store, feature_id=1, project_id=1, number=1, rank=1)
    seed_feature(store, feature_id=2, project_id=1, number=2, rank=2)
    seed_feature(store, feature_id=3, project_id=1, number=3, rank=3)
    seed_feature(store, feature_id=4, project_id=2, number=1, rank=1)
    seed_membership(store, sprint_id=1, feature_id=1, rank=1)
    seed_membership(store, sprint_id=1, feature_id=2, rank=2)
    factory = FakeUnitOfWorkFactory(store)
    handler = ReorderSprintMembership(factory, fixed_clock)

    with pytest.raises(DuplicateIdentifiersError):
        await handler(sprint_id=1, feature_ids=[1, 1])
    with pytest.raises(IncompleteReorderError):
        await handler(sprint_id=1, feature_ids=[1])
    with pytest.raises(FeatureNotFoundError):
        await handler(sprint_id=1, feature_ids=[1, 404])
    with pytest.raises(CrossProjectFeatureError):
        await handler(sprint_id=1, feature_ids=[1, 4])
    with pytest.raises(FeatureNotInSprintError):
        await handler(sprint_id=1, feature_ids=[1, 3])

    assert factory.store.memberships[(1, 1)].sprint_rank == 1
    assert factory.store.memberships[(1, 2)].sprint_rank == 2
    assert factory.store.audit_events == []


async def test_reorder_sprint_membership_rejects_a_missing_sprint() -> None:
    factory = FakeUnitOfWorkFactory()

    with pytest.raises(SprintNotFoundError):
        await ReorderSprintMembership(factory, fixed_clock)(
            sprint_id=404,
            feature_ids=[],
        )


async def test_repository_failure_rolls_back_partial_sprint_ranks() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_sprint(store, sprint_id=1, project_id=1, number=1)
    for feature_id in (1, 2):
        seed_feature(
            store,
            feature_id=feature_id,
            project_id=1,
            number=feature_id,
            rank=feature_id,
        )
        seed_membership(store, sprint_id=1, feature_id=feature_id, rank=feature_id)
    factory = FakeUnitOfWorkFactory(store, fail_sprint_reorder=True)

    with pytest.raises(RuntimeError, match="injected Sprint reorder failure"):
        await ReorderSprintMembership(factory, fixed_clock)(
            sprint_id=1,
            feature_ids=[2, 1],
        )

    assert factory.store.memberships[(1, 1)].sprint_rank == 1
    assert factory.store.memberships[(1, 2)].sprint_rank == 2
    assert factory.store.audit_events == []


async def test_start_sprint_commits_state_and_audit_together() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_sprint(store, sprint_id=1, project_id=1, number=1)
    seed_feature(store, feature_id=1, project_id=1, number=1, rank=1)
    seed_membership(store, sprint_id=1, feature_id=1, rank=1)
    factory = FakeUnitOfWorkFactory(store)

    sprint = await StartSprint(factory, fixed_clock)(sprint_id=1)

    assert sprint.state is SprintState.active
    assert sprint.starts_at == NOW
    assert factory.store.sprints[1].state is SprintState.active
    assert audit_types(factory.store) == ["sprint.started"]
    assert factory.store.audit_events[0].payload == {"sprint_id": 1, "number": 1}


async def test_start_sprint_rejects_a_second_active_sprint_per_project() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_sprint(
        store,
        sprint_id=1,
        project_id=1,
        number=1,
        state=SprintState.active,
    )
    seed_sprint(store, sprint_id=2, project_id=1, number=2)
    factory = FakeUnitOfWorkFactory(store)

    with pytest.raises(ActiveSprintExistsError) as captured:
        await StartSprint(factory, fixed_clock)(sprint_id=2)

    assert captured.value.code == "active_sprint_exists"
    assert factory.store.sprints[2].state is SprintState.planned
    assert factory.store.audit_events == []


async def test_starting_the_already_active_sprint_reports_invalid_state() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_sprint(
        store,
        sprint_id=1,
        project_id=1,
        number=1,
        state=SprintState.active,
    )
    factory = FakeUnitOfWorkFactory(store)

    with pytest.raises(SprintNotPlannedError):
        await StartSprint(factory, fixed_clock)(sprint_id=1)

    assert factory.store.sprints[1].starts_at == NOW
    assert factory.store.audit_events == []


async def test_each_project_can_start_its_own_active_sprint() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_project(store, project_id=2, key="TWO")
    seed_sprint(
        store,
        sprint_id=1,
        project_id=1,
        number=1,
        state=SprintState.active,
    )
    seed_sprint(store, sprint_id=2, project_id=2, number=1)
    factory = FakeUnitOfWorkFactory(store)

    started = await StartSprint(factory, fixed_clock)(sprint_id=2)

    assert started.state is SprintState.active
    assert {
        sprint.project_id
        for sprint in factory.store.sprints.values()
        if sprint.state is SprintState.active
    } == {1, 2}


async def test_start_sprint_rejects_corrupt_cross_project_membership() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_project(store, project_id=2, key="TWO")
    seed_sprint(store, sprint_id=1, project_id=1, number=1)
    seed_feature(store, feature_id=2, project_id=2, number=1, rank=1)
    seed_membership(store, sprint_id=1, feature_id=2, rank=1)
    factory = FakeUnitOfWorkFactory(store)

    with pytest.raises(CrossProjectFeatureError):
        await StartSprint(factory, fixed_clock)(sprint_id=1)

    assert factory.store.sprints[1].state is SprintState.planned
    assert factory.store.audit_events == []


async def test_start_sprint_rejects_missing_unapproved_and_nonplanned_sprints() -> None:
    missing_factory = FakeUnitOfWorkFactory()
    with pytest.raises(SprintNotFoundError):
        await StartSprint(missing_factory, fixed_clock)(sprint_id=404)

    unapproved_store = FakeStore()
    seed_project(unapproved_store, project_id=1, key="ONE")
    seed_sprint(unapproved_store, sprint_id=1, project_id=1, number=1)
    seed_feature(
        unapproved_store,
        feature_id=1,
        project_id=1,
        number=1,
        rank=1,
        approval=None,
    )
    seed_membership(unapproved_store, sprint_id=1, feature_id=1, rank=1)
    unapproved_factory = FakeUnitOfWorkFactory(unapproved_store)
    with pytest.raises(DesignApprovalRequiredError):
        await StartSprint(unapproved_factory, fixed_clock)(sprint_id=1)

    completed_store = FakeStore()
    seed_project(completed_store, project_id=1, key="ONE")
    seed_sprint(
        completed_store,
        sprint_id=1,
        project_id=1,
        number=1,
        state=SprintState.completed,
    )
    completed_factory = FakeUnitOfWorkFactory(completed_store)
    with pytest.raises(SprintNotPlannedError):
        await StartSprint(completed_factory, fixed_clock)(sprint_id=1)

    assert unapproved_factory.store.sprints[1].state is SprintState.planned
    assert completed_factory.store.audit_events == []


async def test_get_active_sprint_returns_ranked_features_or_none() -> None:
    store = FakeStore()
    seed_project(store, project_id=1, key="ONE")
    seed_project(store, project_id=2, key="TWO")
    seed_sprint(
        store,
        sprint_id=1,
        project_id=1,
        number=1,
        state=SprintState.active,
    )
    seed_feature(store, feature_id=1, project_id=1, number=1, rank=1)
    seed_feature(store, feature_id=2, project_id=1, number=2, rank=2)
    seed_membership(store, sprint_id=1, feature_id=1, rank=2)
    seed_membership(store, sprint_id=1, feature_id=2, rank=1)
    factory = FakeUnitOfWorkFactory(store)
    handler = GetActiveSprint(factory)

    active = await handler(project_id=1)
    no_active = await handler(project_id=2)

    assert active is not None
    assert active.sprint.id == 1
    assert [feature.id for feature in active.features] == [2, 1]
    assert no_active is None


async def test_get_active_sprint_rejects_a_missing_project() -> None:
    factory = FakeUnitOfWorkFactory()

    with pytest.raises(ProjectNotFoundError):
        await GetActiveSprint(factory)(project_id=404)


async def test_commit_failure_persists_neither_state_nor_audit_history() -> None:
    factory = FakeUnitOfWorkFactory(fail_commit=True)

    with pytest.raises(RuntimeError, match="injected commit failure"):
        await CreateProject(factory, fixed_clock)(
            key="APP",
            name="AgentBoard",
            repository_url="https://example.test/agentboard.git",
            default_branch="main",
        )

    assert factory.store.projects == {}
    assert factory.store.audit_events == []
    assert factory.instances[0].rolled_back is True


def test_default_clock_can_be_made_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    class FixedDateTime:
        @classmethod
        def now(cls, timezone: object) -> datetime:
            assert timezone is UTC
            return NOW

    monkeypatch.setattr(_support, "datetime", FixedDateTime)

    assert _support.utc_now() == NOW
