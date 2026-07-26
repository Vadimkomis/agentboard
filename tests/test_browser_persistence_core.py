"""File-backed integration coverage for the browser-v0 SQLite foundation."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError

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
)
from agentboard.domain.enums import PlanningStage, SprintState
from agentboard.domain.errors import (
    ActiveSprintExistsError,
    DesignApprovalRequiredError,
    PersistenceConflictError,
)
from agentboard.infrastructure import (
    Database,
    downgrade_database,
    downgrade_database_async,
    upgrade_database,
    upgrade_database_async,
)
from agentboard.infrastructure import database as database_adapter
from agentboard.infrastructure import migrations as migration_runner
from agentboard.infrastructure import paths as path_adapter
from agentboard.infrastructure.conflicts import raise_write_conflict
from agentboard.infrastructure.orm import (
    AuditEventRecord,
    FeatureRecord,
    ProjectRecord,
    SprintFeatureRecord,
    SprintRecord,
)
from agentboard.infrastructure.paths import (
    default_data_directory,
    default_database_path,
    resolve_database_path,
)
from agentboard.infrastructure.unit_of_work import SqlAlchemyUnitOfWork

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)


def fixed_clock() -> datetime:
    return NOW


def test_platform_paths_and_explicit_database_override(tmp_path: Path) -> None:
    home = tmp_path / "home"
    mac_data = home / "Library" / "Application Support" / "AgentBoard"
    linux_data = home / ".local" / "share" / "agentboard"
    xdg_data = tmp_path / "xdg" / "agentboard"

    assert default_data_directory(platform="darwin", environ={}, home=home) == mac_data
    assert default_data_directory(platform="linux", environ={}, home=home) == linux_data
    assert (
        default_data_directory(
            platform="linux2",
            environ={"XDG_DATA_HOME": str(tmp_path / "xdg")},
            home=home,
        )
        == xdg_data
    )
    assert default_database_path(platform="darwin", environ={}, home=home) == (
        mac_data / "agentboard.db"
    )
    assert resolve_database_path(tmp_path / "explicit.db") == tmp_path / "explicit.db"

    with pytest.raises(ValueError, match="absolute"):
        default_data_directory(
            platform="linux",
            environ={"XDG_DATA_HOME": "relative"},
            home=home,
        )
    with pytest.raises(RuntimeError, match="supports macOS and Linux"):
        default_data_directory(platform="win32", environ={}, home=home)


def test_alembic_roundtrip_preserves_legacy_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "roundtrip.db"
    database_path.parent.mkdir()
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("CREATE TABLE stories (id INTEGER PRIMARY KEY, title TEXT)")
        connection.execute("INSERT INTO stories (title) VALUES ('legacy')")
        connection.commit()

    upgrade_database(database_path)
    with closing(sqlite3.connect(database_path)) as connection:
        tables = _sqlite_names(connection, "table")
        triggers = _sqlite_names(connection, "trigger")
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()

    assert {
        "projects",
        "features",
        "sprints",
        "sprint_features",
        "audit_events",
        "stories",
    }.issubset(tables)
    assert len(triggers) == 7
    assert version == ("0001_browser_domain",)

    command.check(migration_runner._migration_config(database_path))
    downgrade_database(database_path)
    with closing(sqlite3.connect(database_path)) as connection:
        tables_after = _sqlite_names(connection, "table")
        legacy = connection.execute("SELECT title FROM stories").fetchone()

    assert "stories" in tables_after
    assert "projects" not in tables_after
    assert legacy == ("legacy",)


def test_alembic_offline_upgrade_renders_foundation_sql(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = migration_runner._migration_config(tmp_path / "offline.db")

    command.upgrade(config, "head", sql=True)

    sql = capsys.readouterr().out
    assert "CREATE TABLE projects" in sql
    assert "CREATE TRIGGER trg_sprint_features_project_insert" in sql
    assert "CREATE TRIGGER trg_audit_events_project_insert" in sql
    assert "uq_sprints_one_active_per_project" in sql


def test_alembic_cli_default_creates_the_platform_data_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "platform" / "agentboard.db"
    monkeypatch.setattr(path_adapter, "default_database_path", lambda: database_path)
    config = migration_runner.Config(str(migration_runner._ALEMBIC_CONFIG_PATH))

    command.upgrade(config, "head")

    assert database_path.is_file()


async def test_async_migration_roundtrip_and_runtime_pragmas(tmp_path: Path) -> None:
    database_path = tmp_path / "async.db"
    await upgrade_database_async(database_path)
    database = Database(database_path, busy_timeout_ms=1_234)
    try:
        async with database.session() as session:
            foreign_keys = await session.scalar(text("PRAGMA foreign_keys"))
            journal_mode = await session.scalar(text("PRAGMA journal_mode"))
            busy_timeout = await session.scalar(text("PRAGMA busy_timeout"))
        assert foreign_keys == 1
        assert journal_mode == "wal"
        assert busy_timeout == 1_234
    finally:
        await database.dispose()

    await downgrade_database_async(database_path)
    await upgrade_database_async(database_path)
    with closing(sqlite3.connect(database_path)) as connection:
        assert "projects" in _sqlite_names(connection, "table")


def test_sqlite_connection_hook_configures_and_closes_its_cursor() -> None:
    cursor = RecordingCursor()
    hook = database_adapter._configure_sqlite_connection(2_500)

    hook(RecordingConnection(cursor), object())

    assert cursor.commands == [
        "PRAGMA foreign_keys=ON",
        "PRAGMA journal_mode=WAL",
        "PRAGMA busy_timeout=2500",
    ]
    assert cursor.closed is True


async def test_database_session_rolls_back_and_validates_timeout(tmp_path: Path) -> None:
    database_path = tmp_path / "session.db"
    await upgrade_database_async(database_path)
    database = Database(database_path)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            async with database.session() as session:
                session.add(_project_record("ROLLBACK"))
                await session.flush()
                raise RuntimeError("injected")

        async with database.session() as session:
            assert await session.scalar(select(ProjectRecord.id)) is None
    finally:
        await database.dispose()

    with pytest.raises(ValueError, match="positive"):
        Database(database_path, busy_timeout_ms=0)


async def test_end_to_end_restart_preserves_isolated_ranked_state_and_audits(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "restart.db"
    await upgrade_database_async(database_path)
    database = Database(database_path)
    first_project_id: int
    second_project_id: int
    sprint_id: int
    try:
        factory = database.unit_of_work
        project_one = await _create_project(factory, "ONE")
        project_two = await _create_project(factory, "TWO")
        first_project_id = _required(project_one.id)
        second_project_id = _required(project_two.id)

        one = await _create_feature(factory, first_project_id, "One", approved=True)
        two = await _create_feature(factory, first_project_id, "Two", approved=True)
        three = await _create_feature(factory, first_project_id, "Three", approved=True)
        other = await _create_feature(factory, second_project_id, "Other", approved=True)

        reordered = await ReorderProjectBacklog(factory, fixed_clock)(
            project_id=first_project_id,
            feature_ids=[_required(three.id), _required(one.id), _required(two.id)],
        )
        assert [feature.title for feature in reordered] == ["Three", "One", "Two"]
        assert [feature.rank for feature in reordered] == [1, 2, 3]
        assert other.rank == 1

        sprint = await CreatePlannedSprint(factory, fixed_clock)(
            project_id=first_project_id,
            name="Foundation",
            goal="Persist the plan",
        )
        sprint_id = _required(sprint.id)
        for feature in (one, two, three):
            await AddFeatureToSprint(factory, fixed_clock)(
                sprint_id=sprint_id,
                feature_id=_required(feature.id),
            )
        sprint_features = await ReorderSprintMembership(factory, fixed_clock)(
            sprint_id=sprint_id,
            feature_ids=[_required(two.id), _required(three.id), _required(one.id)],
        )
        assert [feature.title for feature in sprint_features] == ["Two", "Three", "One"]
        await StartSprint(factory, fixed_clock)(sprint_id=sprint_id)

        second_sprint = await CreatePlannedSprint(factory, fixed_clock)(
            project_id=first_project_id,
            name="Blocked",
        )
        with pytest.raises(ActiveSprintExistsError):
            await StartSprint(factory, fixed_clock)(sprint_id=_required(second_sprint.id))
    finally:
        await database.dispose()

    reopened = Database(database_path)
    try:
        factory = reopened.unit_of_work
        backlog = await ListProjectBacklog(factory)(project_id=first_project_id)
        other_backlog = await ListProjectBacklog(factory)(project_id=second_project_id)
        active = await GetActiveSprint(factory)(project_id=first_project_id)
        async with reopened.session() as session:
            events = list(
                await session.scalars(select(AuditEventRecord).order_by(AuditEventRecord.id))
            )

        assert [feature.title for feature in backlog] == ["Three", "One", "Two"]
        assert [feature.title for feature in other_backlog] == ["Other"]
        assert [(feature.number, feature.rank) for feature in other_backlog] == [(1, 1)]
        assert active is not None
        assert active.sprint.id == sprint_id
        assert [feature.title for feature in active.features] == ["Two", "Three", "One"]
        assert [event.event_type for event in events] == [
            "project.created",
            "project.created",
            "feature.created",
            "feature.created",
            "feature.created",
            "feature.created",
            "backlog.reordered",
            "sprint.created",
            "sprint.feature_added",
            "sprint.feature_added",
            "sprint.feature_added",
            "sprint.reordered",
            "sprint.started",
            "sprint.created",
        ]
        assert events[0].payload == {"project_id": first_project_id, "key": "ONE"}
        assert events[6].payload == {
            "feature_ids": [_required(three.id), _required(one.id), _required(two.id)]
        }
        async with reopened.unit_of_work() as uow:
            restored_project = await uow.projects.get(first_project_id)
            restored_sprint = await uow.sprints.get(sprint_id)
        assert restored_project is not None
        assert (
            restored_project.key,
            restored_project.name,
            restored_project.repository_url,
            restored_project.default_branch,
            restored_project.created_at,
        ) == (
            "ONE",
            "Project ONE",
            "https://example.test/ONE.git",
            "main",
            NOW,
        )
        assert restored_sprint is not None
        assert (
            restored_sprint.name,
            restored_sprint.goal,
            restored_sprint.number,
            restored_sprint.state,
            restored_sprint.starts_at,
        ) == (
            "Foundation",
            "Persist the plan",
            1,
            SprintState.active,
            NOW,
        )
    finally:
        await reopened.dispose()


async def test_sqlite_scopes_feature_sprint_numbers_and_active_sprints_per_project(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "scoped.db"
    await upgrade_database_async(database_path)
    database = Database(database_path)
    try:
        factory = database.unit_of_work
        project_one = await _create_project(factory, "ONE")
        project_two = await _create_project(factory, "TWO")
        one_id = _required(project_one.id)
        two_id = _required(project_two.id)

        feature_one = await _create_feature(factory, one_id, "One")
        feature_two = await _create_feature(factory, two_id, "Other one")
        feature_three = await _create_feature(factory, one_id, "Two")
        assert [feature_one.number, feature_two.number, feature_three.number] == [1, 1, 2]

        first_one = await CreatePlannedSprint(factory, fixed_clock)(
            project_id=one_id,
            name="One first",
        )
        first_two = await CreatePlannedSprint(factory, fixed_clock)(
            project_id=two_id,
            name="Two first",
        )
        second_one = await CreatePlannedSprint(factory, fixed_clock)(
            project_id=one_id,
            name="One second",
        )
        assert [first_one.number, first_two.number, second_one.number] == [1, 1, 2]

        await StartSprint(factory, fixed_clock)(sprint_id=_required(first_one.id))
        await StartSprint(factory, fixed_clock)(sprint_id=_required(first_two.id))
        active_one = await GetActiveSprint(factory)(project_id=one_id)
        active_two = await GetActiveSprint(factory)(project_id=two_id)

        assert active_one is not None
        assert active_two is not None
        assert active_one.sprint.id == first_one.id
        assert active_two.sprint.id == first_two.id
        assert active_one.sprint.project_id != active_two.sprint.project_id

        conflicting = database.unit_of_work()
        with pytest.raises(PersistenceConflictError):
            async with conflicting:
                planned = await conflicting.sprints.get(_required(second_one.id))
                assert planned is not None
                planned.state = SprintState.active
                await conflicting.sprints.update(planned)
        async with database.unit_of_work() as uow:
            restored = await uow.sprints.get(_required(second_one.id))
        assert restored is not None
        assert restored.state is SprintState.planned
    finally:
        await database.dispose()


@pytest.mark.parametrize(
    "order",
    [
        (1, 2, 0),
        (0, 2, 1),
        (2, 0, 1),
    ],
)
async def test_sqlite_backlog_reorders_first_middle_and_last_without_scope_leaks(
    tmp_path: Path,
    order: tuple[int, int, int],
) -> None:
    database_path = tmp_path / f"backlog-{'-'.join(map(str, order))}.db"
    await upgrade_database_async(database_path)
    database = Database(database_path)
    try:
        factory = database.unit_of_work
        project = await _create_project(factory, "ONE")
        other_project = await _create_project(factory, "TWO")
        project_id = _required(project.id)
        other_project_id = _required(other_project.id)
        features = [
            await _create_feature(factory, project_id, title, approved=True)
            for title in ("First", "Middle", "Last")
        ]
        other = await _create_feature(factory, other_project_id, "Other", approved=True)
        before = {_required(feature.id): _without_rank(feature) for feature in features}
        other_before = _without_rank(other)
        requested = [_required(features[index].id) for index in order]

        reordered = await ReorderProjectBacklog(factory, fixed_clock)(
            project_id=project_id,
            feature_ids=requested,
        )
        reloaded_other = await ListProjectBacklog(factory)(project_id=other_project_id)

        assert [feature.id for feature in reordered] == requested
        assert [feature.rank for feature in reordered] == [1, 2, 3]
        assert {_required(feature.id): _without_rank(feature) for feature in reordered} == before
        assert len(reloaded_other) == 1
        assert reloaded_other[0].rank == 1
        assert _without_rank(reloaded_other[0]) == other_before
    finally:
        await database.dispose()


@pytest.mark.parametrize(
    "order",
    [
        (1, 2, 0),
        (0, 2, 1),
        (2, 0, 1),
    ],
)
async def test_sqlite_sprint_membership_reorders_first_middle_and_last(
    tmp_path: Path,
    order: tuple[int, int, int],
) -> None:
    database_path = tmp_path / f"sprint-{'-'.join(map(str, order))}.db"
    await upgrade_database_async(database_path)
    database = Database(database_path)
    try:
        factory = database.unit_of_work
        project = await _create_project(factory, "ONE")
        project_id = _required(project.id)
        features = [
            await _create_feature(factory, project_id, title, approved=True)
            for title in ("First", "Middle", "Last")
        ]
        sprint = await CreatePlannedSprint(factory, fixed_clock)(
            project_id=project_id,
            name="Ranked",
        )
        sprint_id = _required(sprint.id)
        for feature in features:
            await AddFeatureToSprint(factory, fixed_clock)(
                sprint_id=sprint_id,
                feature_id=_required(feature.id),
            )
        requested = [_required(features[index].id) for index in order]

        reordered = await ReorderSprintMembership(factory, fixed_clock)(
            sprint_id=sprint_id,
            feature_ids=requested,
        )
        async with database.session() as session:
            ranks = list(
                await session.scalars(
                    select(SprintFeatureRecord.sprint_rank)
                    .where(SprintFeatureRecord.sprint_id == sprint_id)
                    .order_by(SprintFeatureRecord.sprint_rank)
                )
            )

        assert [feature.id for feature in reordered] == requested
        assert ranks == [1, 2, 3]
    finally:
        await database.dispose()


async def test_direct_database_constraints_and_cross_project_triggers(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "constraints.db"
    await upgrade_database_async(database_path)
    database = Database(database_path)
    try:
        await _seed_constraint_records(database)
        invalid_statements = [
            (
                "INSERT INTO projects (key,name,repository_url,default_branch) "
                "VALUES ('ONE','Duplicate','url','main')",
                None,
            ),
            (
                "INSERT INTO features "
                "(project_id,number,title,description,rank,planning_stage,priority) "
                "VALUES (999,1,'Orphan','',1,'inbox','medium')",
                None,
            ),
            (
                "INSERT INTO features "
                "(project_id,number,title,description,rank,planning_stage,priority) "
                "VALUES (1,1,'Number collision','',9,'inbox','medium')",
                None,
            ),
            (
                "INSERT INTO features "
                "(project_id,number,title,description,rank,planning_stage,priority) "
                "VALUES (1,9,'Rank collision','',1,'inbox','medium')",
                None,
            ),
            (
                "INSERT INTO features "
                "(project_id,number,title,description,rank,planning_stage,priority) "
                "VALUES (1,0,'Bad number','',9,'inbox','medium')",
                None,
            ),
            (
                "INSERT INTO features "
                "(project_id,number,title,description,rank,planning_stage,priority) "
                "VALUES (1,9,'Bad rank','',0,'inbox','medium')",
                None,
            ),
            (
                "INSERT INTO features "
                "(project_id,number,title,description,rank,planning_stage,priority,estimate) "
                "VALUES (1,9,'Bad estimate','',9,'inbox','medium',-1)",
                None,
            ),
            (
                "INSERT INTO features "
                "(project_id,number,title,description,rank,planning_stage,priority) "
                "VALUES (1,9,'Bad planning','',9,'unknown','medium')",
                None,
            ),
            (
                "INSERT INTO features "
                "(project_id,number,title,description,rank,planning_stage,"
                "engineering_state,priority) "
                "VALUES (1,9,'Bad engineering','',9,'inbox','unknown','medium')",
                None,
            ),
            (
                "INSERT INTO sprints (project_id,number,name,state) "
                "VALUES (999,1,'Orphan','planned')",
                None,
            ),
            (
                "INSERT INTO sprints (project_id,number,name,state) "
                "VALUES (1,1,'Number collision','planned')",
                None,
            ),
            (
                "INSERT INTO sprints (project_id,number,name,state) "
                "VALUES (1,0,'Bad number','planned')",
                None,
            ),
            (
                "INSERT INTO sprints (project_id,number,name,state) "
                "VALUES (1,9,'Bad state','unknown')",
                None,
            ),
            (
                "INSERT INTO sprints (project_id,number,name,state) "
                "VALUES (1,3,'Second active','active')",
                None,
            ),
            (
                "INSERT INTO sprint_features (sprint_id,feature_id,sprint_rank) VALUES (999,1,9)",
                None,
            ),
            (
                "INSERT INTO sprint_features (sprint_id,feature_id,sprint_rank) VALUES (1,999,9)",
                None,
            ),
            ("INSERT INTO sprint_features (sprint_id,feature_id,sprint_rank) VALUES (1,2,2)", None),
            ("INSERT INTO sprint_features (sprint_id,feature_id,sprint_rank) VALUES (1,4,1)", None),
            ("INSERT INTO sprint_features (sprint_id,feature_id,sprint_rank) VALUES (2,2,0)", None),
            ("INSERT INTO audit_events (project_id,type,payload) VALUES (999,'orphan','{}')", None),
            (
                "INSERT INTO audit_events (project_id,feature_id,type,payload) "
                "VALUES (1,999,'orphan feature','{}')",
                None,
            ),
            (
                "INSERT INTO audit_events (project_id,feature_id,type,payload) "
                "VALUES (1,2,'cross project','{}')",
                None,
            ),
            ("UPDATE audit_events SET feature_id=2 WHERE id=1", None),
            ("UPDATE audit_events SET project_id=2 WHERE id=1", None),
            ("UPDATE sprint_features SET feature_id=2 WHERE sprint_id=1 AND feature_id=1", None),
            ("UPDATE features SET project_id=2 WHERE id=1", None),
            ("UPDATE features SET project_id=2 WHERE id=5", None),
            ("UPDATE sprints SET project_id=2 WHERE id=1", None),
        ]
        for statement, parameters in invalid_statements:
            with pytest.raises(IntegrityError):
                async with database.session() as session:
                    await session.execute(text(statement), parameters or {})
                    await session.commit()

        async with database.session() as session:
            project_count = await session.scalar(
                select(text("count(*)")).select_from(ProjectRecord)
            )
            membership_count = await session.scalar(
                select(text("count(*)")).select_from(SprintFeatureRecord)
            )
        assert project_count == 2
        assert membership_count == 1
    finally:
        await database.dispose()


async def test_sqlite_foreign_key_delete_actions_preserve_audit_history(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "deletes.db"
    await upgrade_database_async(database_path)
    database = Database(database_path)
    try:
        async with database.session() as session:
            session.add(_project_record("ONE", project_id=1))
            await session.flush()
            session.add(_feature_record(1, 1, project_id=1))
            session.add(_sprint_record(1, 1, project_id=1))
            await session.flush()
            session.add(SprintFeatureRecord(sprint_id=1, feature_id=1, sprint_rank=1))
            session.add(
                AuditEventRecord(
                    project_id=1,
                    feature_id=1,
                    event_type="feature.created",
                    payload={"feature_id": 1},
                    created_at=NOW,
                )
            )
            await session.commit()

        with pytest.raises(IntegrityError):
            async with database.session() as session:
                await session.execute(text("DELETE FROM projects WHERE id=1"))
                await session.commit()

        async with database.session() as session:
            await session.execute(text("DELETE FROM features WHERE id=1"))
            await session.commit()
        async with database.session() as session:
            membership_count = await session.scalar(
                select(text("count(*)")).select_from(SprintFeatureRecord)
            )
            audit_feature_id = await session.scalar(select(AuditEventRecord.feature_id))
        assert membership_count == 0
        assert audit_feature_id is None

        async with database.session() as session:
            session.add(_feature_record(2, 2, project_id=1))
            await session.flush()
            session.add(SprintFeatureRecord(sprint_id=1, feature_id=2, sprint_rank=1))
            await session.commit()
        async with database.session() as session:
            await session.execute(text("DELETE FROM sprints WHERE id=1"))
            await session.commit()
        async with database.session() as session:
            assert (
                await session.scalar(select(text("count(*)")).select_from(SprintFeatureRecord)) == 0
            )

        async with database.session() as session:
            await session.execute(text("DELETE FROM audit_events"))
            await session.execute(text("DELETE FROM projects WHERE id=1"))
            await session.commit()
        async with database.session() as session:
            assert await session.scalar(select(text("count(*)")).select_from(FeatureRecord)) == 0
    finally:
        await database.dispose()


async def test_sqlite_missing_design_rejection_persists_no_membership_or_audit(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "eligibility.db"
    await upgrade_database_async(database_path)
    database = Database(database_path)
    try:
        factory = database.unit_of_work
        project = await _create_project(factory, "ONE")
        project_id = _required(project.id)
        feature = await _create_feature(factory, project_id, "Unapproved")
        sprint = await CreatePlannedSprint(factory, fixed_clock)(
            project_id=project_id,
            name="Planned",
        )

        with pytest.raises(DesignApprovalRequiredError):
            await AddFeatureToSprint(factory, fixed_clock)(
                sprint_id=_required(sprint.id),
                feature_id=_required(feature.id),
            )

        async with database.session() as session:
            memberships = await session.scalar(
                select(text("count(*)")).select_from(SprintFeatureRecord)
            )
            feature_added_audits = await session.scalar(
                select(text("count(*)"))
                .select_from(AuditEventRecord)
                .where(AuditEventRecord.event_type == "sprint.feature_added")
            )
        assert memberships == 0
        assert feature_added_audits == 0
    finally:
        await database.dispose()


async def test_audit_failure_rolls_back_create_and_two_phase_reorder(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "atomic.db"
    await upgrade_database_async(database_path)
    database = Database(database_path)
    try:
        await _install_failing_audit_trigger(database)
        with pytest.raises(PersistenceConflictError):
            await _create_project(database.unit_of_work, "ROLLBACK")
        async with database.session() as session:
            assert await session.scalar(select(ProjectRecord.id)) is None

        await _drop_failing_audit_trigger(database)
        project = await _create_project(database.unit_of_work, "ONE")
        project_id = _required(project.id)
        first = await _create_feature(database.unit_of_work, project_id, "First")
        second = await _create_feature(database.unit_of_work, project_id, "Second")
        await _install_failing_audit_trigger(database)

        with pytest.raises(PersistenceConflictError):
            await ReorderProjectBacklog(database.unit_of_work, fixed_clock)(
                project_id=project_id,
                feature_ids=[_required(second.id), _required(first.id)],
            )

        await _drop_failing_audit_trigger(database)
        backlog = await ListProjectBacklog(database.unit_of_work)(project_id=project_id)
        async with database.session() as session:
            event_types = list(
                await session.scalars(
                    select(AuditEventRecord.event_type).order_by(AuditEventRecord.id)
                )
            )
        assert [feature.title for feature in backlog] == ["First", "Second"]
        assert [feature.rank for feature in backlog] == [1, 2]
        assert event_types == ["project.created", "feature.created", "feature.created"]
    finally:
        await database.dispose()


async def test_unit_of_work_guards_and_conflict_translation(tmp_path: Path) -> None:
    database_path = tmp_path / "uow.db"
    await upgrade_database_async(database_path)
    database = Database(database_path)
    try:
        uow = SqlAlchemyUnitOfWork(database.session_factory)
        with pytest.raises(RuntimeError, match="entered before use"):
            await uow.commit()
        with pytest.raises(RuntimeError, match="entered before use"):
            await uow.flush()
        with pytest.raises(RuntimeError, match="entered before use"):
            await uow.rollback()

        async with uow:
            with pytest.raises(RuntimeError, match="cannot be entered twice"):
                await uow.__aenter__()
            await uow.projects.add(ProjectRecordAdapter.project("ONE"))
            await uow.commit()

        duplicate = SqlAlchemyUnitOfWork(database.session_factory)
        with pytest.raises(PersistenceConflictError):
            async with duplicate:
                await duplicate.projects.add(ProjectRecordAdapter.project("ONE"))
        assert duplicate._session is None

        clean = SqlAlchemyUnitOfWork(database.session_factory)
        async with clean:
            await clean.features.reorder(999, [])
            await clean.sprints.reorder_features(999, [])
            with pytest.raises(ValueError, match="unpersisted Sprint"):
                await clean.sprints.update(_unpersisted_sprint())
            await clean.rollback()
            await clean.flush()

        flush_conflict = SqlAlchemyUnitOfWork(database.session_factory)
        with pytest.raises(PersistenceConflictError):
            async with flush_conflict:
                assert flush_conflict._session is not None
                flush_conflict._session.add(_project_record("ONE"))
                await flush_conflict.flush()

        commit_conflict = SqlAlchemyUnitOfWork(database.session_factory)
        with pytest.raises(PersistenceConflictError):
            async with commit_conflict:
                assert commit_conflict._session is not None
                commit_conflict._session.add(_project_record("ONE"))
                await commit_conflict.commit()
    finally:
        await database.dispose()


def test_write_conflict_translation_handles_integrity_and_sqlite_busy_errors() -> None:
    integrity = IntegrityError(
        "INSERT",
        {},
        sqlite3.IntegrityError("unique constraint failed"),
    )
    busy = OperationalError(
        "UPDATE",
        {},
        sqlite3.OperationalError("database is locked"),
    )
    other = OperationalError(
        "UPDATE",
        {},
        sqlite3.OperationalError("disk I/O error"),
    )

    with pytest.raises(PersistenceConflictError):
        raise_write_conflict(integrity)
    with pytest.raises(PersistenceConflictError):
        raise_write_conflict(busy)
    with pytest.raises(OperationalError) as captured:
        raise_write_conflict(other)
    assert captured.value is other


class ProjectRecordAdapter:
    """Keeps the UoW guard test focused on a domain Project input."""

    @staticmethod
    def project(key: str):
        from agentboard.domain.entities import Project

        return Project(
            key=key,
            name=key,
            repository_url=f"https://example.test/{key}.git",
            default_branch="main",
            created_at=NOW,
            updated_at=NOW,
        )


class RecordingCursor:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.closed = False

    def execute(self, command_text: str) -> None:
        self.commands.append(command_text)

    def close(self) -> None:
        self.closed = True


class RecordingConnection:
    def __init__(self, cursor: RecordingCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> RecordingCursor:
        return self._cursor


async def _create_project(factory, key: str):
    return await CreateProject(factory, fixed_clock)(
        key=key,
        name=f"Project {key}",
        repository_url=f"https://example.test/{key}.git",
        default_branch="main",
    )


async def _create_feature(factory, project_id: int, title: str, *, approved: bool = False):
    return await CreateFeature(factory, fixed_clock)(
        project_id=project_id,
        title=title,
        description=f"{title} description",
        planning_stage=PlanningStage.design_review,
        approved_design_hash="design-sha" if approved else None,
    )


async def _seed_constraint_records(database: Database) -> None:
    async with database.session() as session:
        session.add_all(
            [
                _project_record("ONE", project_id=1),
                _project_record("TWO", project_id=2),
            ]
        )
        await session.flush()
        session.add_all(
            [
                _feature_record(1, 1, project_id=1),
                _feature_record(2, 1, project_id=2),
                _feature_record(3, 2, project_id=2),
                _feature_record(4, 2, project_id=1),
                _feature_record(5, 3, project_id=1),
            ]
        )
        session.add_all(
            [
                _sprint_record(1, 1, project_id=1, state=SprintState.active),
                _sprint_record(2, 1, project_id=2),
            ]
        )
        await session.flush()
        session.add(SprintFeatureRecord(sprint_id=1, feature_id=1, sprint_rank=1))
        session.add(
            AuditEventRecord(
                project_id=1,
                feature_id=1,
                event_type="feature.created",
                payload={"feature_id": 1},
                created_at=NOW,
            )
        )
        session.add(
            AuditEventRecord(
                project_id=1,
                feature_id=5,
                event_type="feature.created",
                payload={"feature_id": 5},
                created_at=NOW,
            )
        )
        await session.commit()


def _project_record(key: str, *, project_id: int | None = None) -> ProjectRecord:
    return ProjectRecord(
        id=project_id,
        key=key,
        name=key,
        repository_url=f"https://example.test/{key}.git",
        default_branch="main",
        created_at=NOW,
        updated_at=NOW,
    )


def _feature_record(
    feature_id: int,
    number: int,
    *,
    project_id: int,
) -> FeatureRecord:
    return FeatureRecord(
        id=feature_id,
        project_id=project_id,
        number=number,
        title=f"Feature {feature_id}",
        description="",
        rank=number,
        planning_stage=PlanningStage.design_review.value,
        engineering_state=None,
        priority="medium",
        estimate=1,
        owner=None,
        approved_design_hash="design-sha",
        completed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _sprint_record(
    sprint_id: int,
    number: int,
    *,
    project_id: int,
    state: SprintState = SprintState.planned,
) -> SprintRecord:
    return SprintRecord(
        id=sprint_id,
        project_id=project_id,
        number=number,
        name=f"Sprint {sprint_id}",
        goal=None,
        state=state.value,
        starts_at=NOW if state is SprintState.active else None,
        ends_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _unpersisted_sprint():
    from agentboard.domain.entities import Sprint

    return Sprint(
        project_id=1,
        number=1,
        name="Unpersisted",
        goal=None,
        state=SprintState.planned,
        starts_at=None,
        ends_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


async def _install_failing_audit_trigger(database: Database) -> None:
    async with database.session() as session:
        await session.execute(
            text(
                "CREATE TRIGGER fail_audit_insert BEFORE INSERT ON audit_events "
                "BEGIN SELECT RAISE(ABORT, 'injected audit failure'); END"
            )
        )
        await session.commit()


async def _drop_failing_audit_trigger(database: Database) -> None:
    async with database.session() as session:
        await session.execute(text("DROP TRIGGER IF EXISTS fail_audit_insert"))
        await session.commit()


def _sqlite_names(connection: sqlite3.Connection, object_type: str) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = ?",
        (object_type,),
    )
    return {row[0] for row in rows}


def _required(identifier: int | None) -> int:
    assert identifier is not None
    return identifier


def _without_rank(feature) -> dict[str, object]:
    snapshot = asdict(feature)
    del snapshot["rank"]
    return snapshot
