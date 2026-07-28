"""Behavioral edge coverage for the loopback browser application."""

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
from agentboard.domain.errors import (
    DuplicateIdentifiersError,
    InvalidInputError,
    PersistenceConflictError,
)
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
from agentboard.web import WebSettings, create_app
from agentboard.web import app as web_app
from agentboard.web.security import CsrfSession, verify_session

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
SESSION_SECRET = "test-session-secret-that-is-long-enough-for-hmac"


def _settings(path: Path, **overrides: Any) -> WebSettings:
    values: dict[str, Any] = {
        "database_path": path,
        "session_secret": SESSION_SECRET,
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


def _hidden_value(html: str, name: str) -> str:
    marker = f'name="{name}" value="'
    start = html.index(marker) + len(marker)
    return html[start : html.index('"', start)]


def _cookie_csrf(client: httpx.AsyncClient) -> str:
    session = verify_session(SESSION_SECRET, client.cookies.get("agentboard_session"))
    assert session is not None
    return session.csrf_token


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
async def test_async_browser_routes_render_navigation_without_authentication(
    tmp_path: Path,
) -> None:
    path = tmp_path / "routes.db"
    _project_id, future_id = await _seed_browser(path)

    async with _web_client(path) as client:
        root = await client.get("/")
        projects = await client.get("/projects")
        backlog = await client.get("/projects/AB/backlog")
        board = await client.get("/projects/AB/board")
        detail = await client.get(f"/projects/AB/features/{future_id}")
        approvals = await client.get("/projects/AB/approvals")
        reports = await client.get("/projects/AB/reports")

    assert root.headers["location"] == "/projects"
    assert "AgentBoard" in projects.text
    assert "Current work" in backlog.text
    assert 'data-board-column="ready_for_engineering"' in board.text
    assert "Future work" in detail.text
    assert "Design approval" in approvals.text
    assert "Sprint 0" in reports.text


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
        catalog = await empty_client.get("/projects")
    async with _web_client(project_path) as client:
        backlog = await client.get("/projects/AB/backlog")
        board = await client.get("/projects/AB/board")

    assert catalog.status_code == 200
    assert "No projects yet" in catalog.text
    assert "No sprint is active for this project" in backlog.text
    assert board.text.count("data-board-column=") == 5
    assert "No work in this state" in board.text
    assert "<title>Board · AgentBoard · AgentBoard</title>" in board.text
    assert "<h1>Board</h1>" in board.text
    assert "<span>Board</span>" in board.text


def _bare_request(
    *,
    headers: list[tuple[bytes, bytes]] | None = None,
    receive: Any = None,
    app: object | None = None,
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
    if app is not None:
        scope["app"] = app
    return Request(scope, receive=receive)


def _form_request(app: object, body: bytes) -> Request:
    messages = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive() -> dict[str, object]:
        return messages.pop(0)

    return _bare_request(
        headers=[(b"content-type", b"application/x-www-form-urlencoded")],
        receive=receive,
        app=app,
    )


def test_missing_csrf_middleware_state_fails_explicitly() -> None:
    request = _bare_request()
    request.state.csrf_session = None

    with pytest.raises(RuntimeError, match="did not initialize"):
        web_app._csrf_session(request)


@pytest.mark.asyncio
async def test_direct_urlencoded_form_parser_accepts_exact_values_and_rejects_malformed_bodies(
    tmp_path: Path,
) -> None:
    app = create_app(_settings(tmp_path / "direct-forms.db"))
    accepted = await web_app._urlencoded_form(
        _form_request(
            app,
            (b"csrf_token=direct-csrf&expected_version=1&idempotency_key=direct&feature_ids=11"),
        )
    )

    with pytest.raises(HTTPException) as malformed_reorder:
        await web_app._urlencoded_form(_form_request(app, b"csrf_token=\xff"))

    assert accepted["feature_ids"] == ["11"]
    assert malformed_reorder.value.status_code == 400


@pytest.mark.asyncio
async def test_backlog_reorder_rejects_unsupported_content_type(tmp_path: Path) -> None:
    path = tmp_path / "unsupported-reorder.db"
    await _seed_browser(path)

    async with _web_client(path) as client:
        response = await client.post(
            "/projects/AB/backlog/reorder",
            content=b"csrf_token=missing-content-type",
        )

    assert response.status_code == 415


@pytest.mark.asyncio
async def test_project_creation_rejects_unsupported_malformed_and_ambiguous_forms(
    tmp_path: Path,
) -> None:
    path = tmp_path / "invalid-project-forms.db"
    await _seed_browser(path)

    async with _web_client(path) as client:
        catalog = await client.get("/projects")
        csrf = _hidden_value(catalog.text, "csrf_token")
        unsupported = await client.post("/projects", content=b"key=NEW")
        malformed = await client.post(
            "/projects",
            content=b"csrf_token=%FF",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        missing = await client.post(
            "/projects",
            content=f"csrf_token={csrf}",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )
        ambiguous = await client.post(
            "/projects",
            content=(
                f"csrf_token={csrf}&key=ONE&key=TWO&name=Ambiguous"
                "&repository_url=https%3A%2F%2Fexample.test%2Frepository"
                "&default_branch=main"
            ),
            headers={"content-type": "application/x-www-form-urlencoded"},
        )

    assert [
        unsupported.status_code,
        malformed.status_code,
        missing.status_code,
        ambiguous.status_code,
    ] == [415, 400, 400, 400]


@pytest.mark.asyncio
async def test_direct_project_creation_handler_covers_success_and_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, _future, _workspace, _detail, _approval, _report = _view_models()
    claims = CsrfSession(csrf_token="direct-csrf", issued_at=1, expires_at=2)
    app = create_app(_settings(tmp_path / "direct-project.db"))
    body = (
        b"csrf_token=direct-csrf&key=AB&name=AgentBoard"
        b"&repository_url=https%3A%2F%2Fexample.test%2Fagentboard&default_branch=main"
    )

    monkeypatch.setattr(web_app, "_uow_factory", lambda _request: object())
    monkeypatch.setattr(web_app, "CreateProject", lambda _factory: _ImmediateQuery(project))
    created = await web_app._create_project(_form_request(app, body), claims)

    monkeypatch.setattr(
        web_app,
        "CreateProject",
        lambda _factory: _ImmediateQuery(error=InvalidInputError("Invalid Project.")),
    )
    monkeypatch.setattr(web_app, "ListProjects", lambda _factory: _ImmediateQuery([]))
    invalid = await web_app._create_project(_form_request(app, body), claims)

    assert created.status_code == 303
    assert created.headers["location"] == "/projects/AB/backlog"
    assert invalid.status_code == 400
    assert "Invalid Project." in invalid.body.decode()


@pytest.mark.asyncio
async def test_direct_reorder_handler_accepts_the_exact_future_backlog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _project, _future, workspace, _detail, _approval, _report = _view_models()
    claims = CsrfSession(csrf_token="direct-csrf", issued_at=1, expires_at=2)
    app = create_app(_settings(tmp_path / "direct-reorder.db"))

    async def load_workspace(_request: Request, _project_key: str) -> ProjectWorkspace:
        return workspace

    monkeypatch.setattr(web_app, "_workspace", load_workspace)
    monkeypatch.setattr(web_app, "_uow_factory", lambda _request: object())
    monkeypatch.setattr(
        web_app,
        "ReorderProjectBacklog",
        lambda _factory: _ImmediateQuery(),
    )
    response = await web_app._reorder_backlog(
        _form_request(
            app,
            (b"csrf_token=direct-csrf&expected_version=1&idempotency_key=direct&feature_ids=11"),
        ),
        "AB",
        claims,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/projects/AB/backlog"


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
        await client.get("/projects/AB/backlog")
        csrf = _cookie_csrf(client)
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
        ({"session_secret": None}, "at least 32 bytes"),
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


def test_web_settings_default_to_an_ephemeral_csrf_session_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "agentboard.web.settings.secrets.token_urlsafe",
        lambda size: "x" * size,
    )

    settings = WebSettings(database_path=tmp_path / "settings.db")

    assert settings.session_secret == "x" * 32


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
