"""Behavioral edge coverage for the owner-only browser application."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import delete, update
from sqlalchemy.exc import OperationalError
from starlette.requests import Request

from agentboard.application import (
    AddFeatureToSprint,
    CreateFeature,
    CreatePlannedSprint,
    CreateProject,
    ReorderProjectBacklog,
    StartSprint,
)
from agentboard.application.views import (
    PendingApproval,
    ProjectFeature,
    ProjectReport,
    ProjectWorkspace,
)
from agentboard.domain.entities import ActiveSprint, Feature, Project, Sprint
from agentboard.domain.enums import EngineeringState, PlanningStage, SprintState
from agentboard.domain.errors import DuplicateIdentifiersError, PersistenceConflictError
from agentboard.infrastructure.database import Database
from agentboard.infrastructure.migrations import upgrade_database
from agentboard.infrastructure.orm import (
    CommandReceiptRecord,
    FeatureRecord,
    SprintRecord,
)
from agentboard.infrastructure.repositories import (
    SqlAlchemyFeatureRepository,
    SqlAlchemyProjectRepository,
)
from agentboard.web import WebSettings, create_app, hash_owner_password
from agentboard.web import app as web_app

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
PASSWORD = "correct-horse-battery-staple"
PASSWORD_HASH = hash_owner_password(
    PASSWORD,
    salt=bytes.fromhex("00112233445566778899aabbccddeeff"),
    iterations=100_000,
)


def _settings(path: Path, **overrides: Any) -> WebSettings:
    values: dict[str, Any] = {
        "database_path": path,
        "owner_password_hash": PASSWORD_HASH,
        "session_secret": "test-session-secret-that-is-long-enough-for-hmac",
        "allowed_hosts": ("testserver",),
        "secure_cookies": False,
    }
    values.update(overrides)
    return WebSettings(**values)


@asynccontextmanager
async def _web_client(path: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(_settings(path))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            follow_redirects=False,
        ) as client:
            yield client


async def _login(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/login",
        content=f"password={PASSWORD}&next=%2Fprojects",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 303


def _hidden_value(html: str, name: str) -> str:
    marker = f'name="{name}" value="'
    start = html.index(marker) + len(marker)
    return html[start : html.index('"', start)]


async def _seed_browser(path: Path) -> tuple[int, int]:
    upgrade_database(path)
    database = Database(path)
    try:
        project = await CreateProject(database.unit_of_work, lambda: NOW)(
            key="AB",
            name="AgentBoard",
            repository_url="https://github.com/example/agentboard",
            default_branch="main",
        )
        await CreateProject(database.unit_of_work, lambda: NOW)(
            key="ZZ",
            name="Other",
            repository_url="https://github.com/example/other",
            default_branch="main",
        )
        future = await _feature(database, project.id, "Future work")
        current = await _feature(
            database,
            project.id,
            "Current work",
            approved_design_hash="design-current",
        )
        human = await _feature(
            database,
            project.id,
            "Human review",
            approved_design_hash="design-human",
        )
        done = await _feature(
            database,
            project.id,
            "Done this sprint",
            approved_design_hash="design-done",
        )
        design = await _feature(
            database,
            project.id,
            "Design approval",
            planning_stage=PlanningStage.design_review,
        )
        sprint = await CreatePlannedSprint(database.unit_of_work, lambda: NOW)(
            project_id=project.id,
            name="Sprint 1",
        )
        for feature in (current, human, done):
            await AddFeatureToSprint(database.unit_of_work, lambda: NOW)(
                sprint_id=sprint.id,
                feature_id=feature.id,
            )
        await StartSprint(database.unit_of_work, lambda: NOW)(sprint_id=sprint.id)

        reported = await _feature(
            database,
            project.id,
            "Reported work",
            approved_design_hash="design-reported",
        )
        completed_sprint = await CreatePlannedSprint(database.unit_of_work, lambda: NOW)(
            project_id=project.id,
            name="Sprint 0",
        )
        await AddFeatureToSprint(database.unit_of_work, lambda: NOW)(
            sprint_id=completed_sprint.id,
            feature_id=reported.id,
        )
        async with database.session() as session:
            await session.execute(
                update(FeatureRecord)
                .where(FeatureRecord.id == human.id)
                .values(engineering_state=EngineeringState.human_review.value)
            )
            await session.execute(
                update(FeatureRecord)
                .where(FeatureRecord.id.in_((done.id, reported.id)))
                .values(engineering_state=EngineeringState.done.value, completed_at=NOW)
            )
            await session.execute(
                update(SprintRecord)
                .where(SprintRecord.id == completed_sprint.id)
                .values(state=SprintState.completed.value, ends_at=NOW)
            )
            await session.commit()
        assert design.id is not None
        return project.id, future.id
    finally:
        await database.dispose()


async def _feature(
    database: Database,
    project_id: int,
    title: str,
    *,
    planning_stage: PlanningStage = PlanningStage.inbox,
    approved_design_hash: str | None = None,
):
    return await CreateFeature(database.unit_of_work, lambda: NOW)(
        project_id=project_id,
        title=title,
        description=f"{title} description",
        planning_stage=planning_stage,
        priority="high",
        estimate=3,
        owner="Owner",
        approved_design_hash=approved_design_hash,
    )


class _ImmediateQuery:
    def __init__(self, value: object = None, *, error: Exception | None = None) -> None:
        self._value = value
        self._error = error

    async def __call__(self, **_kwargs: object) -> object:
        if self._error is not None:
            raise self._error
        return self._value


def _view_models(
    *, project_id: int | None = 1
) -> tuple[
    Project,
    Feature,
    ProjectWorkspace,
    ProjectFeature,
    PendingApproval,
    ProjectReport,
]:
    project = Project(
        id=project_id,
        key="AB",
        name="AgentBoard",
        repository_url="https://github.com/example/agentboard",
        default_branch="main",
        created_at=NOW,
        updated_at=NOW,
    )
    current = Feature(
        id=10,
        project_id=1,
        number=10,
        title="Immediate current",
        description="Current work",
        rank=1,
        planning_stage=PlanningStage.design_review,
        engineering_state=EngineeringState.working,
        priority="high",
        estimate=3,
        owner="Owner",
        approved_design_hash="design-current",
        completed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    done = Feature(
        id=12,
        project_id=1,
        number=12,
        title="Immediate done",
        description="Completed work",
        rank=3,
        planning_stage=PlanningStage.design_review,
        engineering_state=EngineeringState.done,
        priority="medium",
        estimate=2,
        owner="Owner",
        approved_design_hash="design-done",
        completed_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    future = Feature(
        id=11,
        project_id=1,
        number=11,
        title="Immediate future",
        description="Future work",
        rank=2,
        planning_stage=PlanningStage.design_review,
        engineering_state=None,
        priority="high",
        estimate=None,
        owner=None,
        approved_design_hash=None,
        completed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    sprint = Sprint(
        id=1,
        project_id=1,
        number=1,
        name="Sprint 1",
        goal="Exercise the browser boundary",
        state=SprintState.active,
        starts_at=NOW,
        ends_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    workspace = ProjectWorkspace(
        project=project,
        active_sprint=ActiveSprint(sprint, (current, done)),
        future_backlog=(future,),
    )
    detail = ProjectFeature(project, future, None, ())
    approval = PendingApproval("design", future, None, False)
    report_sprint = Sprint(
        id=2,
        project_id=1,
        number=0,
        name="Sprint 0",
        goal=None,
        state=SprintState.completed,
        starts_at=NOW,
        ends_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    report = ProjectReport(report_sprint, (done,))
    return project, future, workspace, detail, approval, report


def _install_immediate_queries(
    monkeypatch: pytest.MonkeyPatch,
    *,
    project_id: int | None = 1,
    reorder_error: Exception | None = None,
) -> None:
    project, _future, workspace, detail, approval, report = _view_models(project_id=project_id)
    monkeypatch.setattr(web_app, "ListProjects", lambda _factory: _ImmediateQuery([project]))
    monkeypatch.setattr(
        web_app,
        "GetProjectWorkspace",
        lambda _factory: _ImmediateQuery(workspace),
    )
    monkeypatch.setattr(
        web_app,
        "GetProjectFeature",
        lambda _factory: _ImmediateQuery(detail),
    )
    monkeypatch.setattr(
        web_app,
        "ListProjectApprovals",
        lambda _factory: _ImmediateQuery([approval]),
    )
    monkeypatch.setattr(
        web_app,
        "ListProjectReports",
        lambda _factory: _ImmediateQuery([report]),
    )
    monkeypatch.setattr(
        web_app,
        "ReorderProjectBacklog",
        lambda _factory: _ImmediateQuery(error=reorder_error),
    )


@pytest.mark.asyncio
async def test_routes_render_immediate_application_results_without_async_portal_gaps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_immediate_queries(monkeypatch)

    async with _web_client(tmp_path / "immediate-routes.db") as client:
        await _login(client)
        projects = await client.get("/projects")
        backlog = await client.get("/projects/AB/backlog")
        board = await client.get("/projects/AB/board")
        detail = await client.get("/projects/AB/features/11")
        approvals = await client.get("/projects/AB/approvals")
        reports = await client.get("/projects/AB/reports")
        csrf = _hidden_value(backlog.text, "csrf_token")
        reorder = await client.post(
            "/projects/AB/backlog/reorder",
            content=(
                f"csrf_token={csrf}&expected_version=1&idempotency_key=immediate&feature_ids=11"
            ),
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    assert "AgentBoard" in projects.text
    assert "Immediate current" in backlog.text
    assert "Immediate done" in board.text
    assert "Immediate future" in detail.text
    assert "Design approval" in approvals.text
    assert "Sprint 0" in reports.text
    assert reorder.status_code == 303


@pytest.mark.asyncio
async def test_conflicting_immediate_reorder_renders_the_latest_backlog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_immediate_queries(monkeypatch, reorder_error=PersistenceConflictError())

    async with _web_client(tmp_path / "immediate-conflict.db") as client:
        await _login(client)
        backlog = await client.get("/projects/AB/backlog")
        csrf = _hidden_value(backlog.text, "csrf_token")
        response = await client.post(
            "/projects/AB/backlog/reorder",
            content=(
                f"csrf_token={csrf}&expected_version=1&idempotency_key=conflict&feature_ids=11"
            ),
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    assert response.status_code == 409
    assert "Immediate future" in response.text
    assert "conflicts with another request" in response.text


@pytest.mark.asyncio
async def test_invalid_immediate_reorder_renders_a_safe_domain_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_immediate_queries(monkeypatch, reorder_error=DuplicateIdentifiersError())

    async with _web_client(tmp_path / "immediate-domain-error.db") as client:
        await _login(client)
        backlog = await client.get("/projects/AB/backlog")
        csrf = _hidden_value(backlog.text, "csrf_token")
        response = await client.post(
            "/projects/AB/backlog/reorder",
            content=(
                f"csrf_token={csrf}&expected_version=1&idempotency_key=invalid&feature_ids=11"
            ),
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    assert response.status_code == 400
    assert "exact current future backlog" in response.text


@pytest.mark.asyncio
async def test_reorder_rejects_an_unpersisted_project_read_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_immediate_queries(monkeypatch, project_id=None)

    async with _web_client(tmp_path / "unpersisted-project.db") as client:
        await _login(client)
        backlog = await client.get("/projects/AB/backlog")
        csrf = _hidden_value(backlog.text, "csrf_token")
        with pytest.raises(RuntimeError, match="must have an identifier"):
            await client.post(
                "/projects/AB/backlog/reorder",
                content=(
                    f"csrf_token={csrf}&expected_version=1"
                    "&idempotency_key=unpersisted&feature_ids=11"
                ),
                headers={"content-type": "application/x-www-form-urlencoded"},
            )


@pytest.mark.asyncio
async def test_async_browser_routes_render_navigation_and_end_the_session(
    tmp_path: Path,
) -> None:
    path = tmp_path / "routes.db"
    _project_id, future_id = await _seed_browser(path)

    async with _web_client(path) as client:
        login_page = await client.get("/login?next=/projects/AB/board")
        await _login(client)
        root = await client.get("/")
        projects = await client.get("/projects")
        backlog = await client.get("/projects/AB/backlog")
        board = await client.get("/projects/AB/board")
        detail = await client.get(f"/projects/AB/features/{future_id}")
        approvals = await client.get("/projects/AB/approvals")
        reports = await client.get("/projects/AB/reports")
        csrf = _hidden_value(projects.text, "csrf_token")
        logout = await client.post(
            "/logout",
            content=f"csrf_token={csrf}",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    assert login_page.status_code == 200
    assert root.headers["location"] == "/projects"
    assert "AgentBoard" in projects.text
    assert "Current work" in backlog.text
    assert 'data-board-column="ready_for_engineering"' in board.text
    assert "Future work" in detail.text
    assert "Design approval" in approvals.text
    assert "Sprint 0" in reports.text
    assert logout.status_code == 303
    assert logout.headers["location"] == "/login"
    assert "agentboard_session=" in logout.headers["set-cookie"]
    assert "Max-Age=0" in logout.headers["set-cookie"]


@pytest.mark.asyncio
async def test_empty_catalog_and_project_without_a_sprint_render_valid_empty_states(
    tmp_path: Path,
) -> None:
    empty_path = tmp_path / "empty.db"
    project_path = tmp_path / "project.db"
    upgrade_database(project_path)
    database = Database(project_path)
    try:
        await CreateProject(database.unit_of_work, lambda: NOW)(
            key="AB",
            name="AgentBoard",
            repository_url="https://github.com/example/agentboard",
            default_branch="main",
        )
    finally:
        await database.dispose()

    async with _web_client(empty_path) as empty_client:
        await _login(empty_client)
        catalog = await empty_client.get("/projects")
    async with _web_client(project_path) as client:
        await _login(client)
        backlog = await client.get("/projects/AB/backlog")
        board = await client.get("/projects/AB/board")

    assert catalog.status_code == 200
    assert "No projects yet" in catalog.text
    assert "No sprint is active for this project" in backlog.text
    assert board.text.count("data-board-column=") == 5
    assert "No work in this state" in board.text


@pytest.mark.asyncio
async def test_anonymous_query_is_preserved_as_a_local_post_login_destination(
    tmp_path: Path,
) -> None:
    async with _web_client(tmp_path / "anonymous.db") as client:
        response = await client.get("/projects?view=all")

    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=%2Fprojects%3Fview%3Dall"


@pytest.mark.asyncio
async def test_login_rejects_unsupported_and_malformed_form_bodies(tmp_path: Path) -> None:
    async with _web_client(tmp_path / "login-forms.db") as client:
        unsupported = await client.post("/login", content="password=x")
        malformed = await client.post(
            "/login",
            content="password",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    assert unsupported.status_code == 415
    assert malformed.status_code == 400


@pytest.mark.asyncio
async def test_login_offloads_password_verification_from_the_event_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    async def verify(password: str, encoded: str) -> bool:
        calls.append((password, encoded))
        return True

    monkeypatch.setattr(web_app, "_verify_owner_password_async", verify)
    async with _web_client(tmp_path / "offloaded-login.db") as client:
        response = await client.post(
            "/login",
            content="password=anything&next=%2Fprojects",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    assert response.status_code == 303
    assert calls == [("anything", PASSWORD_HASH)]


def _bare_request(
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    receive: Any = None,
) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": headers or [],
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
    }
    return Request(scope, receive=receive)


@pytest.mark.asyncio
async def test_bounded_form_stream_rejects_an_undeclared_oversized_body() -> None:
    messages = [
        {
            "type": "http.request",
            "body": b"x" * 16_385,
            "more_body": False,
        }
    ]

    async def receive() -> dict[str, object]:
        return messages.pop(0)

    with pytest.raises(HTTPException) as raised:
        await web_app._bounded_body(_bare_request(receive=receive))

    assert raised.value.status_code == 400


@pytest.mark.parametrize("value", [b"invalid", b"-1"])
def test_form_content_length_must_be_a_non_negative_integer(value: bytes) -> None:
    request = _bare_request(headers=[(b"content-length", value)])

    with pytest.raises(HTTPException) as raised:
        web_app._content_length(request)

    assert raised.value.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        b"x" * 16_385,
        b"csrf_token=%FF",
        b"csrf_token",
    ],
)
async def test_backlog_reorder_rejects_oversized_or_malformed_forms(
    tmp_path: Path,
    body: bytes,
) -> None:
    path = tmp_path / "malformed-reorder.db"
    await _seed_browser(path)
    async with _web_client(path) as client:
        await _login(client)
        response = await client.post(
            "/projects/AB/backlog/reorder",
            content=body,
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "form",
    [
        "csrf_token={csrf}&idempotency_key=key&feature_ids=1",
        "csrf_token={csrf}&expected_version=1&feature_ids=1",
        "csrf_token={csrf}&expected_version=1&idempotency_key=&feature_ids=1",
        "csrf_token={csrf}&expected_version=1&idempotency_key=key&feature_ids=1,,2",
        "csrf_token={csrf}&expected_version=invalid&idempotency_key=key&feature_ids=1",
        "csrf_token={csrf}&expected_version=0&idempotency_key=key&feature_ids=1",
        (
            "csrf_token={csrf}&csrf_token={csrf}&expected_version=1"
            "&idempotency_key=key&feature_ids=1"
        ),
    ],
)
async def test_backlog_reorder_rejects_ambiguous_or_invalid_values(
    tmp_path: Path,
    form: str,
) -> None:
    path = tmp_path / "invalid-values.db"
    await _seed_browser(path)
    async with _web_client(path) as client:
        await _login(client)
        backlog = await client.get("/projects/AB/backlog")
        csrf = _hidden_value(backlog.text, "csrf_token")
        response = await client.post(
            "/projects/AB/backlog/reorder",
            content=form.format(csrf=csrf),
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_empty_future_backlog_can_be_submitted_as_an_exact_empty_order(
    tmp_path: Path,
) -> None:
    path = tmp_path / "empty-order.db"
    upgrade_database(path)
    database = Database(path)
    try:
        await CreateProject(database.unit_of_work, lambda: NOW)(
            key="AB",
            name="AgentBoard",
            repository_url="https://github.com/example/agentboard",
            default_branch="main",
        )
    finally:
        await database.dispose()

    async with _web_client(path) as client:
        await _login(client)
        page = await client.get("/projects/AB/backlog")
        csrf = _hidden_value(page.text, "csrf_token")
        response = await client.post(
            "/projects/AB/backlog/reorder",
            content=(
                f"csrf_token={csrf}&expected_version=1&idempotency_key=empty-order&feature_ids="
            ),
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    assert response.status_code == 303


@pytest.mark.asyncio
async def test_invalid_exact_backlog_order_returns_a_safe_domain_error(
    tmp_path: Path,
) -> None:
    path = tmp_path / "domain-error.db"
    await _seed_browser(path)
    async with _web_client(path) as client:
        await _login(client)
        page = await client.get("/projects/AB/backlog")
        csrf = _hidden_value(page.text, "csrf_token")
        response = await client.post(
            "/projects/AB/backlog/reorder",
            content=(
                f"csrf_token={csrf}&expected_version=1"
                "&idempotency_key=invalid-order&feature_ids=999"
            ),
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    assert response.status_code == 400
    assert "exact current future backlog" in response.text


@pytest.mark.asyncio
async def test_idempotency_key_reuse_returns_a_safe_conflict(tmp_path: Path) -> None:
    path = tmp_path / "idempotency-conflict.db"
    _project_id, future_id = await _seed_browser(path)
    async with _web_client(path) as client:
        await _login(client)
        page = await client.get("/projects/AB/backlog")
        csrf = _hidden_value(page.text, "csrf_token")
        first = (
            f"csrf_token={csrf}&expected_version=1"
            f"&idempotency_key=same-key&feature_ids={future_id}%2C5"
        )
        await client.post(
            "/projects/AB/backlog/reorder",
            content=first,
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        conflicting = await client.post(
            "/projects/AB/backlog/reorder",
            content=(
                f"csrf_token={csrf}&expected_version=2"
                f"&idempotency_key=same-key&feature_ids=5%2C{future_id}"
            ),
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    assert conflicting.status_code == 409
    assert "conflicts with another request" in conflicting.text


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"owner_password_hash": ""}, "owner password hash"),
        ({"session_secret": "too-short"}, "at least 32 bytes"),
        ({"allowed_hosts": ()}, "allowed hosts"),
        ({"allowed_hosts": ("",)}, "allowed hosts"),
        ({"session_ttl_seconds": 0}, "session TTL"),
        ({"session_cookie_name": ""}, "session cookie name"),
    ],
)
def test_web_settings_reject_unsafe_values(
    tmp_path: Path,
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _settings(tmp_path / "settings.db", **overrides)


@pytest.mark.asyncio
async def test_feature_repository_empty_lookup_is_a_valid_empty_result(
    tmp_path: Path,
) -> None:
    path = tmp_path / "empty-lookup.db"
    upgrade_database(path)
    database = Database(path)
    try:
        async with database.session() as session:
            repository = SqlAlchemyFeatureRepository(session)
            assert await repository.list_by_ids(1, []) == []
    finally:
        await database.dispose()


class _LockedScalarSession:
    async def scalar(self, _statement: object) -> None:
        raise OperationalError(
            "UPDATE projects",
            {},
            sqlite3.OperationalError("database is locked"),
        )


@pytest.mark.asyncio
async def test_project_version_lock_contention_is_a_typed_write_conflict() -> None:
    repository = SqlAlchemyProjectRepository(_LockedScalarSession())  # type: ignore[arg-type]

    with pytest.raises(PersistenceConflictError):
        await repository.increment_version(1, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corrupt_result",
    [
        {"feature_ids": "not-a-list"},
        {"feature_ids": [True]},
    ],
)
async def test_reorder_replay_rejects_a_malformed_persisted_receipt(
    tmp_path: Path,
    corrupt_result: dict[str, object],
) -> None:
    path = tmp_path / "malformed-receipt.db"
    project_id, future_id = await _seed_browser(path)
    database = Database(path)
    try:
        command = ReorderProjectBacklog(database.unit_of_work, lambda: NOW)
        await command(
            project_id=project_id,
            feature_ids=[future_id, 5],
            idempotency_key="receipt",
        )
        async with database.session() as session:
            await session.execute(
                update(CommandReceiptRecord)
                .where(CommandReceiptRecord.idempotency_key == "receipt")
                .values(result=corrupt_result)
            )
            await session.commit()

        with pytest.raises(RuntimeError, match="receipt is malformed"):
            await command(
                project_id=project_id,
                feature_ids=[future_id, 5],
                idempotency_key="receipt",
            )
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_reorder_replay_rejects_receipt_references_to_deleted_work(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing-receipt-feature.db"
    project_id, future_id = await _seed_browser(path)
    database = Database(path)
    try:
        command = ReorderProjectBacklog(database.unit_of_work, lambda: NOW)
        await command(
            project_id=project_id,
            feature_ids=[future_id, 5],
            idempotency_key="receipt",
        )
        async with database.session() as session:
            await session.execute(delete(FeatureRecord).where(FeatureRecord.id == future_id))
            await session.commit()

        with pytest.raises(RuntimeError, match="refers to missing Features"):
            await command(
                project_id=project_id,
                feature_ids=[future_id, 5],
                idempotency_key="receipt",
            )
    finally:
        await database.dispose()
