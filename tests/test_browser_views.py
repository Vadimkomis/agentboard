"""Integration tests for browser-facing application read models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, update

from agentboard.application import (
    AddFeatureToSprint,
    CreateFeature,
    CreatePlannedSprint,
    CreateProject,
    GetProjectFeature,
    GetProjectWorkspace,
    ListProjectApprovals,
    ListProjectReports,
    ReorderProjectBacklog,
    StartSprint,
)
from agentboard.application.views import presented_engineering_state
from agentboard.domain.enums import EngineeringState, PlanningStage, SprintState
from agentboard.domain.errors import (
    FeatureNotFoundError,
    IdempotencyConflictError,
    ProjectNotFoundError,
    StaleRecordVersionError,
)
from agentboard.infrastructure.database import Database
from agentboard.infrastructure.migrations import upgrade_database
from agentboard.infrastructure.orm import (
    AuditEventRecord,
    CommandReceiptRecord,
    FeatureRecord,
    SprintRecord,
)
from agentboard.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)


@pytest.fixture
async def browser_database(tmp_path: Path):
    path = tmp_path / "browser-views.db"
    upgrade_database(path)
    database = Database(path)
    try:
        yield database
    finally:
        await database.dispose()


async def _project(database: Database, key: str, name: str):
    return await CreateProject(database.unit_of_work, lambda: NOW)(
        key=key,
        name=name,
        repository_url=f"https://github.com/example/{key.lower()}",
        default_branch="main",
    )


async def _feature(
    database: Database,
    project_id: int,
    title: str,
    *,
    stage: PlanningStage = PlanningStage.inbox,
    approved: str | None = None,
):
    return await CreateFeature(database.unit_of_work, lambda: NOW)(
        project_id=project_id,
        title=title,
        description=f"{title} description",
        planning_stage=stage,
        priority="high",
        estimate=3,
        owner="Vadim",
        approved_design_hash=approved,
    )


async def test_presented_engineering_state_uses_only_available_durable_facts(
    browser_database: Database,
) -> None:
    project = await _project(browser_database, "AB", "AgentBoard")
    unapproved = await _feature(browser_database, project.id, "Unapproved")
    approved = await _feature(
        browser_database,
        project.id,
        "Approved",
        approved="design-a",
    )

    assert presented_engineering_state(unapproved, in_active_sprint=True) is None
    assert (
        presented_engineering_state(approved, in_active_sprint=True)
        is EngineeringState.ready_for_engineering
    )
    assert presented_engineering_state(approved, in_active_sprint=False) is None

    approved.engineering_state = EngineeringState.working
    assert presented_engineering_state(approved, in_active_sprint=True) is EngineeringState.working

    approved.engineering_state = None
    approved.completed_at = NOW
    assert presented_engineering_state(approved, in_active_sprint=True) is EngineeringState.done


@pytest.mark.asyncio
async def test_workspace_is_one_project_scoped_snapshot(browser_database: Database) -> None:
    project_b = await _project(browser_database, "ZZ", "Other project")
    project_a = await _project(browser_database, "AB", "AgentBoard")
    future = await _feature(browser_database, project_a.id, "Future work")
    active = await _feature(browser_database, project_a.id, "Current work", approved="design-a")
    await _feature(browser_database, project_b.id, "PROJECT_B_MUST_NOT_LEAK")
    sprint = await CreatePlannedSprint(browser_database.unit_of_work, lambda: NOW)(
        project_id=project_a.id,
        name="Sprint 1",
        goal="Ship the browser",
    )
    await AddFeatureToSprint(browser_database.unit_of_work, lambda: NOW)(
        sprint_id=sprint.id,
        feature_id=active.id,
    )
    await StartSprint(browser_database.unit_of_work, lambda: NOW)(sprint_id=sprint.id)

    workspace = await GetProjectWorkspace(browser_database.unit_of_work)(project_key="AB")

    assert not hasattr(workspace, "projects")
    assert workspace.project == project_a
    assert workspace.active_sprint is not None
    assert workspace.active_sprint.sprint.id == sprint.id
    assert [item.id for item in workspace.active_sprint.features] == [active.id]
    assert [item.id for item in workspace.future_backlog] == [future.id]


@pytest.mark.asyncio
async def test_workspace_unknown_key_is_typed_not_found(browser_database: Database) -> None:
    with pytest.raises(ProjectNotFoundError, match="Project 'missing' was not found"):
        await GetProjectWorkspace(browser_database.unit_of_work)(project_key="missing")


@pytest.mark.asyncio
async def test_feature_detail_is_scoped_by_project_key_and_number(
    browser_database: Database,
) -> None:
    project_a = await _project(browser_database, "AB", "AgentBoard")
    project_b = await _project(browser_database, "TJ", "Trail Journal")
    feature_a = await _feature(browser_database, project_a.id, "Safe detail")
    feature_b = await _feature(browser_database, project_b.id, "PROJECT_B_MUST_NOT_LEAK")

    detail = await GetProjectFeature(browser_database.unit_of_work)(
        project_key="AB",
        feature_number=feature_a.number,
    )

    assert detail.project == project_a
    assert detail.feature == feature_a
    assert [event.event_type for event in detail.history] == ["feature.created"]
    with pytest.raises(FeatureNotFoundError):
        await GetProjectFeature(browser_database.unit_of_work)(
            project_key="AB",
            feature_number=feature_b.number + 1,
        )


@pytest.mark.asyncio
async def test_feature_detail_includes_active_sprint_membership(
    browser_database: Database,
) -> None:
    project = await _project(browser_database, "AB", "AgentBoard")
    feature = await _feature(browser_database, project.id, "Sprint detail", approved="design-a")
    sprint = await CreatePlannedSprint(browser_database.unit_of_work, lambda: NOW)(
        project_id=project.id,
        name="Sprint 1",
    )
    await AddFeatureToSprint(browser_database.unit_of_work, lambda: NOW)(
        sprint_id=sprint.id,
        feature_id=feature.id,
    )
    await StartSprint(browser_database.unit_of_work, lambda: NOW)(sprint_id=sprint.id)
    planned = await CreatePlannedSprint(browser_database.unit_of_work, lambda: NOW)(
        project_id=project.id,
        name="Sprint 2",
    )
    await AddFeatureToSprint(browser_database.unit_of_work, lambda: NOW)(
        sprint_id=planned.id,
        feature_id=feature.id,
    )

    detail = await GetProjectFeature(browser_database.unit_of_work)(
        project_key="AB",
        feature_number=feature.number,
    )

    assert detail.sprint is not None
    assert detail.sprint.id == sprint.id
    assert detail.sprint.state is SprintState.active


@pytest.mark.asyncio
async def test_pending_approvals_are_deterministic_and_project_scoped(
    browser_database: Database,
) -> None:
    project = await _project(browser_database, "AB", "AgentBoard")
    other = await _project(browser_database, "TJ", "Trail Journal")
    design = await _feature(
        browser_database,
        project.id,
        "Approve the design",
        stage=PlanningStage.design_review,
    )
    human = await _feature(browser_database, project.id, "Approve the PR", approved="design-b")
    await _feature(
        browser_database,
        project.id,
        "Already approved",
        stage=PlanningStage.design_review,
        approved="design-c",
    )
    await _feature(
        browser_database,
        other.id,
        "PROJECT_B_MUST_NOT_LEAK",
        stage=PlanningStage.design_review,
    )
    completed_by_timestamp = await _feature(
        browser_database,
        project.id,
        "Completed timestamp",
        stage=PlanningStage.design_review,
        approved="design-d",
    )
    completed_by_state = await _feature(
        browser_database,
        project.id,
        "Completed state",
        stage=PlanningStage.design_review,
    )
    async with browser_database.session() as session:
        await session.execute(
            update(FeatureRecord)
            .where(FeatureRecord.id == human.id)
            .values(engineering_state=EngineeringState.human_review.value)
        )
        await session.execute(
            update(FeatureRecord)
            .where(FeatureRecord.id == completed_by_timestamp.id)
            .values(
                engineering_state=EngineeringState.human_review.value,
                completed_at=NOW,
            )
        )
        await session.execute(
            update(FeatureRecord)
            .where(FeatureRecord.id == completed_by_state.id)
            .values(engineering_state=EngineeringState.done.value)
        )
        await session.commit()

    approvals = await ListProjectApprovals(browser_database.unit_of_work)(project_key="AB")

    assert [(item.kind, item.feature.id) for item in approvals] == [
        ("design", design.id),
        ("pull_request", human.id),
    ]
    assert all(item.subject_revision is None for item in approvals)
    assert all(item.actionable is False for item in approvals)


@pytest.mark.asyncio
async def test_reports_include_only_completed_sprint_history(
    browser_database: Database,
) -> None:
    project = await _project(browser_database, "AB", "AgentBoard")
    other = await _project(browser_database, "TJ", "Trail Journal")
    completed = await _feature(browser_database, project.id, "Completed work", approved="design-a")
    incomplete = await _feature(browser_database, project.id, "Not completed", approved="design-d")
    active = await _feature(browser_database, project.id, "Still active", approved="design-b")
    leaked = await _feature(browser_database, other.id, "PROJECT_B_MUST_NOT_LEAK", approved="x")
    completed_sprint = await CreatePlannedSprint(browser_database.unit_of_work, lambda: NOW)(
        project_id=project.id,
        name="Sprint 1",
    )
    active_sprint = await CreatePlannedSprint(browser_database.unit_of_work, lambda: NOW)(
        project_id=project.id,
        name="Sprint 2",
    )
    other_sprint = await CreatePlannedSprint(browser_database.unit_of_work, lambda: NOW)(
        project_id=other.id,
        name="Other Sprint",
    )
    for sprint, feature in (
        (completed_sprint, completed),
        (completed_sprint, incomplete),
        (active_sprint, active),
        (other_sprint, leaked),
    ):
        await AddFeatureToSprint(browser_database.unit_of_work, lambda: NOW)(
            sprint_id=sprint.id,
            feature_id=feature.id,
        )
    async with browser_database.session() as session:
        await session.execute(
            update(SprintRecord)
            .where(SprintRecord.id == completed_sprint.id)
            .values(state=SprintState.completed.value, ends_at=NOW)
        )
        await session.execute(
            update(FeatureRecord)
            .where(FeatureRecord.id == completed.id)
            .values(engineering_state=EngineeringState.done.value, completed_at=NOW)
        )
        await session.commit()
    await StartSprint(browser_database.unit_of_work, lambda: NOW)(sprint_id=active_sprint.id)

    reports = await ListProjectReports(browser_database.unit_of_work)(project_key="AB")

    assert len(reports) == 1
    assert reports[0].sprint.id == completed_sprint.id
    assert [item.id for item in reports[0].features] == [completed.id]


@pytest.mark.asyncio
async def test_reports_attribute_rollover_completion_only_to_its_completion_sprint(
    browser_database: Database,
) -> None:
    project = await _project(browser_database, "AB", "AgentBoard")
    feature = await _feature(browser_database, project.id, "Rollover work", approved="design-a")
    first = await CreatePlannedSprint(browser_database.unit_of_work, lambda: NOW)(
        project_id=project.id,
        name="Sprint 1",
    )
    second = await CreatePlannedSprint(browser_database.unit_of_work, lambda: NOW)(
        project_id=project.id,
        name="Sprint 2",
    )
    for sprint in (first, second):
        await AddFeatureToSprint(browser_database.unit_of_work, lambda: NOW)(
            sprint_id=sprint.id,
            feature_id=feature.id,
        )
    first_end = NOW + timedelta(days=7)
    second_start = NOW + timedelta(days=8)
    completion = NOW + timedelta(days=10)
    async with browser_database.session() as session:
        await session.execute(
            update(SprintRecord)
            .where(SprintRecord.id == first.id)
            .values(
                state=SprintState.completed.value,
                starts_at=NOW,
                ends_at=first_end,
            )
        )
        await session.execute(
            update(SprintRecord)
            .where(SprintRecord.id == second.id)
            .values(
                state=SprintState.completed.value,
                starts_at=second_start,
                ends_at=completion,
            )
        )
        await session.execute(
            update(FeatureRecord)
            .where(FeatureRecord.id == feature.id)
            .values(
                engineering_state=EngineeringState.done.value,
                completed_at=completion,
            )
        )
        await session.commit()

    reports = await ListProjectReports(browser_database.unit_of_work)(project_key="AB")

    assert [item.id for item in reports[0].features] == []
    assert [item.id for item in reports[1].features] == [feature.id]


@pytest.mark.asyncio
async def test_view_queries_reconstruct_from_a_new_database_instance(tmp_path: Path) -> None:
    path = tmp_path / "restart.db"
    upgrade_database(path)
    first = Database(path)
    project = await _project(first, "AB", "AgentBoard")
    feature = await _feature(first, project.id, "Durable view")
    await first.dispose()
    second = Database(path)
    try:
        workspace = await GetProjectWorkspace(second.unit_of_work)(project_key="AB")
        detail = await GetProjectFeature(second.unit_of_work)(
            project_key="AB",
            feature_number=feature.number,
        )
        assert [item.title for item in workspace.future_backlog] == ["Durable view"]
        assert detail.feature.title == "Durable view"
    finally:
        await second.dispose()


@pytest.mark.asyncio
async def test_browser_reorder_is_versioned_durable_and_idempotent(
    browser_database: Database,
) -> None:
    project = await _project(browser_database, "AB", "AgentBoard")
    first = await _feature(browser_database, project.id, "First")
    second = await _feature(browser_database, project.id, "Second")
    command = ReorderProjectBacklog(browser_database.unit_of_work, lambda: NOW)

    reordered = await command(
        project_id=project.id,
        feature_ids=[second.id, first.id],
        expected_version=1,
        idempotency_key="reorder-1",
    )
    replayed = await command(
        project_id=project.id,
        feature_ids=[second.id, first.id],
        expected_version=1,
        idempotency_key="reorder-1",
    )
    workspace = await GetProjectWorkspace(browser_database.unit_of_work)(project_key="AB")
    async with browser_database.session() as session:
        event_count = len(
            list(
                await session.scalars(
                    select(AuditEventRecord).where(
                        AuditEventRecord.event_type == "backlog.reordered"
                    )
                )
            )
        )

    assert [item.id for item in reordered] == [second.id, first.id]
    assert [item.id for item in replayed] == [second.id, first.id]
    assert workspace.project.version == 2
    assert event_count == 1


@pytest.mark.asyncio
async def test_browser_reorder_rolls_back_every_write_when_commit_fails_late(
    browser_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await _project(browser_database, "AB", "AgentBoard")
    first = await _feature(browser_database, project.id, "First")
    second = await _feature(browser_database, project.id, "Second")

    async def fail_after_all_writes_are_flushed(
        unit_of_work: SqlAlchemyUnitOfWork,
    ) -> None:
        await unit_of_work.flush()
        raise RuntimeError("simulated late persistence failure")

    monkeypatch.setattr(
        SqlAlchemyUnitOfWork,
        "commit",
        fail_after_all_writes_are_flushed,
    )

    with pytest.raises(RuntimeError, match="simulated late persistence failure"):
        await ReorderProjectBacklog(browser_database.unit_of_work, lambda: NOW)(
            project_id=project.id,
            feature_ids=[second.id, first.id],
            expected_version=1,
            idempotency_key="reorder-rollback",
        )

    workspace = await GetProjectWorkspace(browser_database.unit_of_work)(project_key="AB")
    async with browser_database.session() as session:
        receipt = await session.scalar(
            select(CommandReceiptRecord).where(
                CommandReceiptRecord.idempotency_key == "reorder-rollback"
            )
        )
        reorder_event = await session.scalar(
            select(AuditEventRecord).where(AuditEventRecord.event_type == "backlog.reordered")
        )

    assert workspace.project.version == 1
    assert [feature.id for feature in workspace.future_backlog] == [first.id, second.id]
    assert receipt is None
    assert reorder_event is None


@pytest.mark.asyncio
async def test_browser_reorder_rejects_stale_version_and_key_reuse(
    browser_database: Database,
) -> None:
    project = await _project(browser_database, "AB", "AgentBoard")
    first = await _feature(browser_database, project.id, "First")
    second = await _feature(browser_database, project.id, "Second")
    command = ReorderProjectBacklog(browser_database.unit_of_work, lambda: NOW)
    await command(
        project_id=project.id,
        feature_ids=[second.id, first.id],
        expected_version=1,
        idempotency_key="reorder-1",
    )

    with pytest.raises(IdempotencyConflictError):
        await command(
            project_id=project.id,
            feature_ids=[first.id, second.id],
            expected_version=2,
            idempotency_key="reorder-1",
        )
    with pytest.raises(StaleRecordVersionError):
        await command(
            project_id=project.id,
            feature_ids=[first.id, second.id],
            expected_version=1,
            idempotency_key="reorder-2",
        )

    workspace = await GetProjectWorkspace(browser_database.unit_of_work)(project_key="AB")
    assert [item.id for item in workspace.future_backlog] == [second.id, first.id]
    assert workspace.project.version == 2
